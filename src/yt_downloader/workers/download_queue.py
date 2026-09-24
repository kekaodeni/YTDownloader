"""A bounded shared queue with one existing QThread worker per active download."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
import logging
import threading
import time
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from yt_downloader.core.errors import (
    AppError,
    CancellationCleanupReport,
    OperationCancelled,
    OperationPaused,
)
from yt_downloader.core.models import DownloadProgress, DownloadRequest, DownloadResult, TaskStatus


logger = logging.getLogger(__name__)
_PAUSABLE = {TaskStatus.DOWNLOADING_VIDEO, TaskStatus.DOWNLOADING_AUDIO}


class _TaskControl:
    """Event-compatible stop token with an explicit pause/cancel distinction."""

    def __init__(self):
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._changed = threading.Event()
        self._status = TaskStatus.PENDING
        self._lock = threading.Lock()

    def is_set(self):
        return self._cancel.is_set() or self._pause.is_set()

    def set(self):
        self._cancel.set()
        self._changed.set()

    def wait(self, timeout=None):
        return self._changed.wait(timeout)

    def is_cancelled(self):
        return self._cancel.is_set()

    def is_paused(self):
        return self._pause.is_set()

    def set_status(self, status):
        with self._lock:
            self._status = status

    def pause(self):
        with self._lock:
            if self._status not in _PAUSABLE or self.is_set():
                return False
            self._pause.set()
            self._changed.set()
            return True


class DownloadServiceProtocol(Protocol):
    def download(self, request: DownloadRequest, progress_callback, cancel_event: threading.Event) -> DownloadResult: ...


class _DownloadWorker(QObject):
    progress = Signal(object)
    finished = Signal()

    def __init__(self, service: DownloadServiceProtocol, request: DownloadRequest, cancel_event: _TaskControl) -> None:
        super().__init__()
        self.service = service
        self.request = request
        self.cancel_event = cancel_event
        self.outcome: tuple[str, object | None] | None = None

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.download(self.request, self.progress.emit, self.cancel_event)
            self.outcome = ("completed", result)
        except OperationCancelled as exc:
            report = exc.cleanup_report or CancellationCleanupReport(
                task_id=self.request.task_id,
                output_directory=str(self.request.output_directory),
            )
            self.outcome = ("cancelled", report)
        except OperationPaused:
            self.outcome = ("paused", None)
        except AppError as exc:
            self.outcome = ("failed", exc)
        except Exception as exc:  # Last-resort worker boundary; never cross Qt with an uncaught exception.
            error = AppError("worker_failed", "下载任务意外失败。", repr(exc))
            self.outcome = ("failed", error)
        finally:
            self.finished.emit()


class DownloadQueueController(QObject):
    """One global capacity limit shared by single downloads and all batches."""
    task_queued = Signal(object)
    task_started = Signal(str)
    pausing = Signal(str)
    paused = Signal(str)
    resuming = Signal(str)
    cancelling = Signal(str)
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str, object)
    cancelled = Signal(str, object)
    busy_changed = Signal(bool)

    def __init__(self, service, parent=None, *, max_concurrent=2):
        super().__init__(parent)
        if max_concurrent not in {1, 2, 3, 4}:
            raise ValueError('Download concurrency must be 1–4')
        self._service = service
        self._pending = deque()
        self._active = {}
        self._paused_tasks = {}
        self.max_concurrent = max_concurrent
        self._paused = set()

    @property
    def is_busy(self):
        return bool(self._active or self._pending or self._paused_tasks)

    @property
    def active_task_id(self):
        return next(iter(self._active), None)

    @property
    def pending_count(self):
        return len(self._pending)

    def task_position(self, task_id):
        if task_id in self._active:
            return 'active'
        if task_id in self._paused_tasks:
            return 'paused'
        return 'pending' if any(request.task_id == task_id for request in self._pending) else None

    def set_concurrency(self, value):
        if value not in {1, 2, 3, 4}:
            raise ValueError('Download concurrency must be 1–4')
        self.max_concurrent = value
        self._start_next()

    @Slot(object)
    def enqueue(self, request):
        if self.task_position(request.task_id):
            raise ValueError('Task is already queued')
        was_busy = self.is_busy
        self._pending.append(request)
        self.task_queued.emit(request)
        if not was_busy:
            self.busy_changed.emit(True)
        self._start_next()

    def pause(self, batch_id=''):
        self._paused.add(batch_id)

    def resume(self, batch_id=''):
        self._paused.discard(batch_id)
        self._start_next()

    def pause_task(self, task_id):
        active = self._active.get(task_id)
        if not active or not active[3].pause():
            return False
        self.pausing.emit(task_id)
        return True

    def resume_task(self, task_id):
        request = self._paused_tasks.pop(task_id, None)
        if request is None:
            return False
        self._pending.appendleft(replace(request, resume_partial=True))
        self.resuming.emit(task_id)
        self._start_next()
        return True

    @staticmethod
    def _cleanup_partial(request):
        from yt_downloader.services.task_artifacts import TaskArtifactRegistry
        return TaskArtifactRegistry(request.output_directory, request.task_id).cleanup()

    def cancel(self, task_id):
        active = self._active.get(task_id)
        if active:
            request, thread, worker, cancel = active
            if not cancel.is_set():
                cancel.set()
                self.cancelling.emit(task_id)
            return True
        paused = self._paused_tasks.pop(task_id, None)
        if paused is not None:
            self.cancelling.emit(task_id)
            self.cancelled.emit(task_id, self._cleanup_partial(paused))
            if not self.is_busy:
                self.busy_changed.emit(False)
            return True
        for request in tuple(self._pending):
            if request.task_id == task_id:
                self._pending.remove(request)
                self.cancelling.emit(task_id)
                report = self._cleanup_partial(request) if request.resume_partial else CancellationCleanupReport(task_id, str(request.output_directory))
                self.cancelled.emit(task_id, report)
                if not self.is_busy:
                    self.busy_changed.emit(False)
                return True
        return False

    def cancel_all(self, batch_id=None):
        requests = [*self._pending, *(item[0] for item in self._active.values()), *self._paused_tasks.values()]
        for request in requests:
            if batch_id is None or getattr(request, 'batch_id', '') == batch_id:
                self.cancel(request.task_id)

    def _start_next(self):
        while len(self._active) < self.max_concurrent and self._pending:
            request = next((item for item in self._pending if '' not in self._paused
                            and getattr(item, 'batch_id', '') not in self._paused), None)
            if request is None:
                break
            self._pending.remove(request)
            cancel = _TaskControl()
            thread = QThread(self)
            thread.setObjectName(f'download-{request.task_id}')
            worker = _DownloadWorker(self._service, request, cancel)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._forward_progress)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(self._thread_finished)
            thread.finished.connect(thread.deleteLater)
            self._active[request.task_id] = (request, thread, worker, cancel)
            if not request.resume_partial:
                self.task_started.emit(request.task_id)
            thread.start()

    @Slot(object)
    def _forward_progress(self, progress):
        active = self._active.get(progress.task_id)
        if active:
            active[3].set_status(progress.status)
            if not active[3].is_set():
                self.progress.emit(progress)

    @Slot()
    def _thread_finished(self):
        thread = self.sender()
        task_id = next((key for key, item in self._active.items() if item[1] is thread), None)
        if task_id is None:
            return
        # finished is emitted before thread-local destructors finish. Join before
        # releasing Python-owned workers or advertising an idle queue.
        thread.wait()
        request, _, worker, control = self._active.pop(task_id)
        outcome = worker.outcome
        if not outcome:
            self.failed.emit(task_id, AppError('worker_failed', '下载任务意外结束。', 'Worker ended without an outcome'))
        elif outcome[0] == 'completed':
            self.completed.emit(outcome[1])
        elif outcome[0] == 'failed':
            self.failed.emit(task_id, outcome[1])
        elif outcome[0] == 'paused' and not control.is_cancelled():
            self._paused_tasks[task_id] = request
            self.paused.emit(task_id)
        elif outcome[0] == 'paused':
            self.cancelled.emit(task_id, self._cleanup_partial(request))
        else:
            self.cancelled.emit(task_id, outcome[1] or CancellationCleanupReport(task_id, str(request.output_directory)))
        self._start_next()
        if not self.is_busy:
            self.busy_changed.emit(False)

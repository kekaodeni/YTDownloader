"""A bounded shared queue with one existing QThread worker per active download."""

from __future__ import annotations

from collections import deque
import logging
import threading
import time
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from yt_downloader.core.errors import (
    AppError,
    CancellationCleanupReport,
    OperationCancelled,
)
from yt_downloader.core.models import DownloadProgress, DownloadRequest, DownloadResult


logger = logging.getLogger(__name__)


class DownloadServiceProtocol(Protocol):
    def download(self, request: DownloadRequest, progress_callback, cancel_event: threading.Event) -> DownloadResult: ...


class _DownloadWorker(QObject):
    progress = Signal(object)
    finished = Signal()

    def __init__(self, service: DownloadServiceProtocol, request: DownloadRequest, cancel_event: threading.Event) -> None:
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
        self.max_concurrent = max_concurrent
        self._paused = set()

    @property
    def is_busy(self):
        return bool(self._active or self._pending)

    @property
    def active_task_id(self):
        return next(iter(self._active), None)

    @property
    def pending_count(self):
        return len(self._pending)

    def task_position(self, task_id):
        if task_id in self._active:
            return 'active'
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

    def cancel(self, task_id):
        active = self._active.get(task_id)
        if active:
            request, thread, worker, cancel = active
            if not cancel.is_set():
                cancel.set()
                self.cancelling.emit(task_id)
            return True
        for request in tuple(self._pending):
            if request.task_id == task_id:
                self._pending.remove(request)
                self.cancelling.emit(task_id)
                self.cancelled.emit(task_id, CancellationCleanupReport(task_id, str(request.output_directory)))
                if not self.is_busy:
                    self.busy_changed.emit(False)
                return True
        return False

    def cancel_all(self, batch_id=None):
        requests = [*self._pending, *(item[0] for item in self._active.values())]
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
            cancel = threading.Event()
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
            self.task_started.emit(request.task_id)
            thread.start()

    @Slot(object)
    def _forward_progress(self, progress):
        active = self._active.get(progress.task_id)
        if active and not active[3].is_set():
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
        request, _, worker, _ = self._active.pop(task_id)
        outcome = worker.outcome
        if not outcome:
            self.failed.emit(task_id, AppError('worker_failed', '下载任务意外结束。', 'Worker ended without an outcome'))
        elif outcome[0] == 'completed':
            self.completed.emit(outcome[1])
        elif outcome[0] == 'failed':
            self.failed.emit(task_id, outcome[1])
        else:
            self.cancelled.emit(task_id, outcome[1] or CancellationCleanupReport(task_id, str(request.output_directory)))
        self._start_next()
        if not self.is_busy:
            self.busy_changed.emit(False)

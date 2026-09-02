"""A strict single-active-task queue implemented with one QThread per download."""

from __future__ import annotations

from collections import deque
import logging
import threading
import time
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from yt_downloader.core.errors import AppError, OperationCancelled
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
        except OperationCancelled:
            self.outcome = ("cancelled", None)
        except AppError as exc:
            self.outcome = ("failed", exc)
        except Exception as exc:  # Last-resort worker boundary; never cross Qt with an uncaught exception.
            error = AppError("worker_failed", "下载任务意外失败。", repr(exc))
            self.outcome = ("failed", error)
        finally:
            self.finished.emit()


class DownloadQueueController(QObject):
    task_queued = Signal(object)
    task_started = Signal(str)
    cancelling = Signal(str)
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str, object)
    cancelled = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, service: DownloadServiceProtocol, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._pending: deque[DownloadRequest] = deque()
        self._active_request: DownloadRequest | None = None
        self._active_cancel: threading.Event | None = None
        self._active_thread: QThread | None = None
        self._active_worker: _DownloadWorker | None = None
        self._active_cancel_requested_at: float | None = None

    @property
    def is_busy(self) -> bool:
        return bool(self._active_request or self._pending)

    @property
    def active_task_id(self) -> str | None:
        return self._active_request.task_id if self._active_request else None

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @Slot(object)
    def enqueue(self, request: DownloadRequest) -> None:
        was_busy = self.is_busy
        self._pending.append(request)
        self.task_queued.emit(request)
        if not was_busy:
            self.busy_changed.emit(True)
        self._start_next()

    def cancel(self, task_id: str) -> bool:
        if self._active_request and self._active_request.task_id == task_id:
            assert self._active_cancel is not None
            if not self._active_cancel.is_set():
                self._active_cancel.set()
                self._active_cancel_requested_at = time.monotonic()
                logger.info("Cancellation requested for task %s", task_id)
                self.cancelling.emit(task_id)
            return True
        for request in tuple(self._pending):
            if request.task_id == task_id:
                self._pending.remove(request)
                self.cancelling.emit(task_id)
                self.cancelled.emit(task_id)
                if not self.is_busy:
                    self.busy_changed.emit(False)
                return True
        return False

    def cancel_all(self) -> None:
        for request in tuple(self._pending):
            self._pending.remove(request)
            self.cancelling.emit(request.task_id)
            self.cancelled.emit(request.task_id)
        if self._active_cancel:
            if not self._active_cancel.is_set():
                self._active_cancel.set()
                self._active_cancel_requested_at = time.monotonic()
                assert self._active_request is not None
                logger.info("Cancellation requested for task %s", self._active_request.task_id)
                self.cancelling.emit(self._active_request.task_id)
        elif not self.is_busy:
            self.busy_changed.emit(False)

    def _start_next(self) -> None:
        if self._active_request or not self._pending:
            return
        request = self._pending.popleft()
        cancel_event = threading.Event()
        thread = QThread(self)
        thread.setObjectName(f"download-{request.task_id}")
        worker = _DownloadWorker(self._service, request, cancel_event)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._forward_progress)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._active_request = request
        self._active_cancel = cancel_event
        self._active_thread = thread
        self._active_worker = worker
        self.task_started.emit(request.task_id)
        thread.start()

    @Slot(object)
    def _forward_progress(self, progress: DownloadProgress) -> None:
        if not self._active_request or progress.task_id != self._active_request.task_id:
            return
        if self._active_cancel and self._active_cancel.is_set():
            return
        self.progress.emit(progress)

    @Slot()
    def _thread_finished(self) -> None:
        request = self._active_request
        worker = self._active_worker
        outcome = worker.outcome if worker else None
        cancel_requested_at = self._active_cancel_requested_at
        self._active_request = None
        self._active_cancel = None
        self._active_thread = None
        self._active_worker = None
        self._active_cancel_requested_at = None
        if request and cancel_requested_at is not None:
            logger.info(
                "Cancellation cleanup completed for task %s after %.3fs",
                request.task_id,
                time.monotonic() - cancel_requested_at,
            )
        if request and outcome:
            kind, payload = outcome
            if kind == "completed":
                self.completed.emit(payload)
            elif kind == "failed":
                self.failed.emit(request.task_id, payload)
            else:
                self.cancelled.emit(request.task_id)
        elif request:
            self.failed.emit(
                request.task_id,
                AppError("worker_failed", "下载任务意外结束。", "Worker thread ended without an outcome"),
            )
        if self._pending:
            self._start_next()
        else:
            self.busy_changed.emit(False)

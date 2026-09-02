"""A strict single-active-task queue implemented with one QThread per download."""

from __future__ import annotations

from collections import deque
import threading
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from yt_downloader.core.errors import AppError, OperationCancelled
from yt_downloader.core.models import DownloadProgress, DownloadRequest, DownloadResult


class DownloadServiceProtocol(Protocol):
    def download(self, request: DownloadRequest, progress_callback, cancel_event: threading.Event) -> DownloadResult: ...


class _DownloadWorker(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, service: DownloadServiceProtocol, request: DownloadRequest, cancel_event: threading.Event) -> None:
        super().__init__()
        self.service = service
        self.request = request
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.download(self.request, self.progress.emit, self.cancel_event)
            self.completed.emit(result)
        except OperationCancelled:
            self.cancelled.emit()
        except AppError as exc:
            self.failed.emit(exc)
        except Exception as exc:  # Last-resort worker boundary; never cross Qt with an uncaught exception.
            self.failed.emit(AppError("worker_failed", "下载任务意外失败。", repr(exc)))
        finally:
            self.finished.emit()


class DownloadQueueController(QObject):
    task_queued = Signal(object)
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
            self._active_cancel.set()
            return True
        for request in tuple(self._pending):
            if request.task_id == task_id:
                self._pending.remove(request)
                self.cancelled.emit(task_id)
                if not self.is_busy:
                    self.busy_changed.emit(False)
                return True
        return False

    def cancel_all(self) -> None:
        for request in tuple(self._pending):
            self._pending.remove(request)
            self.cancelled.emit(request.task_id)
        if self._active_cancel:
            self._active_cancel.set()
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
        worker.progress.connect(self.progress)
        worker.completed.connect(self.completed)
        worker.failed.connect(lambda error, task_id=request.task_id: self.failed.emit(task_id, error))
        worker.cancelled.connect(lambda task_id=request.task_id: self.cancelled.emit(task_id))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._active_request = request
        self._active_cancel = cancel_event
        self._active_thread = thread
        self._active_worker = worker
        thread.start()

    @Slot()
    def _thread_finished(self) -> None:
        self._active_request = None
        self._active_cancel = None
        self._active_thread = None
        self._active_worker = None
        if self._pending:
            self._start_next()
        else:
            self.busy_changed.emit(False)


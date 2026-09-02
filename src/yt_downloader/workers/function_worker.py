"""Reusable QRunnable for short metadata, probe and thumbnail operations."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(object)
    cancelled = Signal()
    finished = Signal()


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            self.signals.result.emit(self.function(*self.args, **self.kwargs))
        except OperationCancelled:
            self.signals.cancelled.emit()
        except AppError as exc:
            self.signals.error.emit(exc)
        except Exception as exc:
            self.signals.error.emit(AppError(
                "worker_failed",
                "后台操作意外失败。",
                repr(exc),
                ErrorContext(traceback_text=traceback.format_exc(), stage="Background task"),
            ))
        finally:
            self.signals.finished.emit()


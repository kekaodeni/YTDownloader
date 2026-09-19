"""Latest-value GUI dispatch without inventing progress or delaying stages."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from yt_downloader.core.models import DownloadProgress


class ProgressEventCoalescer(QObject):
    dispatched = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pending: dict[str, DownloadProgress] = {}
        self._last_status = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

    @Slot(object)
    def push(self, progress: DownloadProgress) -> None:
        task_id = progress.task_id
        if progress.status != self._last_status.get(task_id):
            pending = self._pending.pop(task_id, None)
            if pending is not None:
                self.dispatched.emit(pending)
            self._last_status[task_id] = progress.status
            self.dispatched.emit(progress)
            return
        self._pending[task_id] = progress
        if not self._timer.isActive():
            self._timer.start(0)

    @Slot()
    def flush(self) -> None:
        pending, self._pending = self._pending, {}
        for progress in pending.values():
            self.dispatched.emit(progress)

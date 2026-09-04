"""Latest-value GUI dispatch without inventing progress or delaying stages."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from yt_downloader.core.models import DownloadProgress


class ProgressEventCoalescer(QObject):
    dispatched = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pending: DownloadProgress | None = None
        self._last_status = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

    @Slot(object)
    def push(self, progress: DownloadProgress) -> None:
        if self._last_status is None:
            self._last_status = progress.status
            self.dispatched.emit(progress)
            return
        pending = self._pending
        if progress.status != self._last_status:
            if pending is not None:
                self._pending = None
                self.dispatched.emit(pending)
            self._last_status = progress.status
            self.dispatched.emit(progress)
            return
        self._pending = progress
        if not self._timer.isActive():
            self._timer.start(0)

    @Slot()
    def flush(self) -> None:
        pending, self._pending = self._pending, None
        if pending is not None:
            self.dispatched.emit(pending)

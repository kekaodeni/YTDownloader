from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from yt_downloader.core.formatting import format_bytes, format_eta, format_speed
from yt_downloader.core.models import DownloadProgress, STATUS_TEXT, TaskStatus
from yt_downloader.ui.typography import FontRole


class ProgressWidget(QWidget):
    """Keeps bar, percentage and speed simultaneously visible for every state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_percent: int | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        top = QHBoxLayout()
        self.status_label = QLabel("等待下载")
        self.status_label.setProperty("secondary", True)
        self.percent_label = QLabel("—%")
        self.percent_label.setProperty("typographyRole", FontRole.NUMERIC.value)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.status_label)
        top.addStretch()
        top.addWidget(self.percent_label)
        root.addLayout(top)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setAccessibleName("下载进度")
        root.addWidget(self.progress_bar)
        bottom = QHBoxLayout()
        self.speed_label = QLabel("—")
        self.speed_label.setProperty("secondary", True)
        self.speed_label.setProperty("typographyRole", FontRole.NUMERIC.value)
        self.size_label = QLabel("— / —")
        self.size_label.setProperty("secondary", True)
        self.size_label.setProperty("typographyRole", FontRole.NUMERIC.value)
        self.eta_label = QLabel("剩余 —")
        self.eta_label.setProperty("secondary", True)
        self.eta_label.setProperty("typographyRole", FontRole.NUMERIC.value)
        bottom.addWidget(self.speed_label)
        bottom.addStretch()
        bottom.addWidget(self.size_label)
        bottom.addSpacing(14)
        bottom.addWidget(self.eta_label)
        root.addLayout(bottom)

    def set_progress(self, progress: DownloadProgress) -> None:
        self.status_label.setText(STATUS_TEXT[progress.status])
        stopping = progress.status in {
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
        if stopping:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(self._last_percent or 0)
            self.percent_label.setText(f"{self._last_percent}%" if self._last_percent is not None else "—%")
        elif progress.percent is None:
            self.progress_bar.setRange(0, 0)
            self.percent_label.setText("—%")
        else:
            value = round(progress.percent)
            self._last_percent = value
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
            self.percent_label.setText(f"{value}%")
        self.speed_label.setText("—" if stopping else format_speed(progress.speed))
        if not stopping or progress.downloaded_bytes is not None or progress.total_bytes is not None:
            total_text = format_bytes(progress.total_bytes)
            if progress.total_is_estimate and progress.total_bytes is not None:
                total_text = f"估算 {total_text}"
            self.size_label.setText(f"{format_bytes(progress.downloaded_bytes)} / {total_text}")
        eta = "—" if stopping else format_eta(progress.eta)
        self.eta_label.setText(f"剩余 {eta}" if eta != "—" else "剩余 —")

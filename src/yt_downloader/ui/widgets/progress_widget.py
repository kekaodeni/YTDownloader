from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from yt_downloader.core.formatting import format_bytes, format_eta, format_speed
from yt_downloader.core.models import DownloadProgress, STATUS_TEXT, TaskStatus
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree, set_typographic_text


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
        apply_typography(self.status_label, FontRole.SECONDARY)
        self.percent_label = QLabel("—%")
        apply_typography(self.percent_label, FontRole.NUMERIC)
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
        apply_typography(self.speed_label, FontRole.NUMERIC)
        self.size_label = QLabel("— / —")
        apply_typography(self.size_label, FontRole.NUMERIC)
        self.eta_label = QLabel("剩余 —")
        apply_typography(self.eta_label, FontRole.NUMERIC)
        bottom.addWidget(self.speed_label)
        bottom.addStretch()
        bottom.addWidget(self.size_label)
        bottom.addSpacing(14)
        bottom.addWidget(self.eta_label)
        root.addLayout(bottom)
        apply_typography_tree(self)

    def set_progress(self, progress: DownloadProgress) -> None:
        set_typographic_text(self.status_label, STATUS_TEXT[progress.status], FontRole.SECONDARY)
        stopping = progress.status in {
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
        if stopping:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(self._last_percent or 0)
            set_typographic_text(
                self.percent_label,
                f"{self._last_percent}%" if self._last_percent is not None else "—%",
                FontRole.NUMERIC,
            )
        elif progress.percent is None:
            self.progress_bar.setRange(0, 0)
            set_typographic_text(self.percent_label, "—%", FontRole.NUMERIC)
        else:
            value = round(progress.percent)
            self._last_percent = value
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
            set_typographic_text(self.percent_label, f"{value}%", FontRole.NUMERIC)
        set_typographic_text(
            self.speed_label, "—" if stopping else format_speed(progress.speed), FontRole.NUMERIC
        )
        if not stopping or progress.downloaded_bytes is not None or progress.total_bytes is not None:
            total_text = format_bytes(progress.total_bytes)
            if progress.total_is_estimate and progress.total_bytes is not None:
                total_text = f"估算 {total_text}"
            set_typographic_text(
                self.size_label,
                f"{format_bytes(progress.downloaded_bytes)} / {total_text}",
                FontRole.NUMERIC,
            )
        eta = "—" if stopping else format_eta(progress.eta)
        set_typographic_text(
            self.eta_label, f"剩余 {eta}" if eta != "—" else "剩余 —", FontRole.NUMERIC
        )

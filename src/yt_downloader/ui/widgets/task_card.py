from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from yt_downloader.core.errors import CancellationCleanupReport
from yt_downloader.core.models import DownloadProgress, DownloadRequest, DownloadResult, STATUS_TEXT, TaskStatus
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree
from yt_downloader.ui.icons import FluentIconService
from yt_downloader.ui.widgets.progress_widget import ProgressWidget


class DownloadTaskCard(QWidget):
    cancel_requested = Signal(str)
    open_file_requested = Signal(str)
    open_folder_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, request: DownloadRequest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.request = request
        self.file_path: Path | None = None
        self.status = TaskStatus.PENDING
        self.setProperty("fluentRole", "card")
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(132, 74)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setProperty("fluentRole", "subtle")
        pixmap = QPixmap()
        if request.video.thumbnail_bytes:
            pixmap.loadFromData(request.video.thumbnail_bytes)
        if not pixmap.isNull():
            self.thumbnail.setPixmap(pixmap.scaled(self.thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            self.thumbnail.setText("视频")
        root.addWidget(self.thumbnail, 0, Qt.AlignmentFlag.AlignTop)
        content = QVBoxLayout()
        content.setSpacing(7)
        self.title_label = QLabel(request.video.title)
        apply_typography(self.title_label, FontRole.CARD_TITLE)
        self.title_label.setWordWrap(True)
        content.addWidget(self.title_label)
        quality = QLabel(f"{request.format.label} · {request.format.container}")
        apply_typography(quality, FontRole.SECONDARY)
        content.addWidget(quality)
        self.progress = ProgressWidget()
        self.progress.set_progress(DownloadProgress(request.task_id, TaskStatus.PENDING))
        content.addWidget(self.progress)
        actions = QHBoxLayout()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setProperty("fluentAppearance", "danger")
        self.cancel_button.setAccessibleName(f"取消下载 {request.video.title}")
        self.cancel_button.clicked.connect(lambda: self.cancel_requested.emit(request.task_id))
        self.open_button = QPushButton("打开文件")
        self.open_button.setVisible(False)
        self.open_button.clicked.connect(lambda: self.open_file_requested.emit(str(self.file_path or "")))
        self.folder_button = QPushButton("打开文件夹")
        self.folder_button.setVisible(False)
        self.folder_button.clicked.connect(lambda: self.open_folder_requested.emit(str(self.file_path or "")))
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.folder_button)
        actions.addStretch()
        content.addLayout(actions)
        root.addLayout(content, 1)
        self.remove_button = QToolButton()
        self._icons = FluentIconService()
        self.remove_button.setIcon(self._icons.icon("delete"))
        self.remove_button.setIconSize(QSize(18, 18))
        self.remove_button.setToolTip("删除任务")
        self.remove_button.setAccessibleName(f"删除任务 {request.video.title}")
        self.remove_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(request.task_id))
        root.addWidget(self.remove_button, 0, Qt.AlignmentFlag.AlignTop)
        apply_typography_tree(self)

    def apply_theme(self, theme: str) -> None:
        self.remove_button.setIcon(self._icons.icon("delete", theme=theme))

    def update_progress(self, progress: DownloadProgress) -> None:
        self.status = progress.status
        self.progress.set_progress(progress)

    def set_cancelling(self) -> None:
        self.status = TaskStatus.CANCELLING
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("正在取消…")
        self.progress.set_progress(DownloadProgress(self.request.task_id, TaskStatus.CANCELLING))

    def set_completed(self, result: DownloadResult) -> None:
        self.status = TaskStatus.COMPLETED
        self.file_path = result.file_path
        self.progress.set_progress(DownloadProgress(result.task_id, TaskStatus.COMPLETED, 100, result.file_size, result.file_size))
        self.cancel_button.hide()
        self.open_button.show()
        self.folder_button.show()

    def set_terminal_status(
        self,
        status: TaskStatus,
        cleanup_report: CancellationCleanupReport | None = None,
    ) -> None:
        self.status = status
        self.progress.set_progress(DownloadProgress(self.request.task_id, status))
        self.cancel_button.hide()
        if (
            status is TaskStatus.CANCELLED
            and cleanup_report is not None
            and not cleanup_report.succeeded
        ):
            self.progress.status_label.setText("已取消，但部分临时文件未能清理")
            self.file_path = Path(cleanup_report.output_directory)
            self.folder_button.show()

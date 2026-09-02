from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from yt_downloader.core.filename import sanitize_filename
from yt_downloader.core.formatting import format_bytes, format_duration
from yt_downloader.core.errors import CancellationCleanupReport
from yt_downloader.core.models import DownloadProgress, DownloadRequest, DownloadResult, TaskStatus, VideoInfo
from yt_downloader.core.url import InvalidYoutubeUrl, normalize_youtube_url
from yt_downloader.ui.widgets.task_card import DownloadTaskCard

if TYPE_CHECKING:
    from yt_downloader.ui.motion import MotionManager


class DownloadPage(QWidget):
    parse_requested = Signal(str)
    download_requested = Signal(object, object, str, str)
    cancel_requested = Signal(str)
    open_file_requested = Signal(str)
    open_folder_requested = Signal(str)

    def __init__(
        self,
        download_directory: str,
        parent: QWidget | None = None,
        *,
        motion: "MotionManager | None" = None,
    ) -> None:
        super().__init__(parent)
        self.motion = motion
        self.video: VideoInfo | None = None
        self.cards: dict[str, DownloadTaskCard] = {}
        self._terminal_task_ids: set[str] = set()
        self._default_directory = download_directory
        self._directory_overridden = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page_host = QWidget()
        root = QVBoxLayout(page_host)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)
        heading = QLabel("下载")
        heading.setProperty("headingLevel", "1")
        root.addWidget(heading)
        subtitle = QLabel("粘贴一个 YouTube 视频链接，选择画质后开始下载。")
        subtitle.setProperty("secondary", True)
        root.addWidget(subtitle)

        url_card = QWidget()
        url_card.setProperty("fluentRole", "card")
        url_layout = QVBoxLayout(url_card)
        url_layout.setContentsMargins(16, 16, 16, 14)
        row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴 YouTube 视频链接……")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.setAccessibleName("YouTube 视频链接")
        self.url_input.returnPressed.connect(self._request_parse)
        self.parse_button = QPushButton("解析")
        self.parse_button.setProperty("fluentAppearance", "primary")
        self.parse_button.setAccessibleName("解析视频链接")
        self.parse_button.clicked.connect(self._request_parse)
        row.addWidget(self.url_input, 1)
        row.addWidget(self.parse_button)
        url_layout.addLayout(row)
        self.clipboard_hint = QLabel("")
        self.clipboard_hint.setProperty("secondary", True)
        self.clipboard_hint.setVisible(False)
        url_layout.addWidget(self.clipboard_hint)
        self.metadata_busy = QProgressBar()
        self.metadata_busy.setRange(0, 0)
        self.metadata_busy.setVisible(False)
        self.metadata_busy.setAccessibleName("正在解析视频")
        url_layout.addWidget(self.metadata_busy)
        root.addWidget(url_card)

        self.video_card = QWidget()
        self.video_card.setProperty("fluentRole", "card")
        self.video_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.video_card.setMinimumHeight(252)
        info_root = QHBoxLayout(self.video_card)
        info_root.setContentsMargins(16, 16, 16, 16)
        info_root.setSpacing(20)
        self.thumbnail = QLabel("缩略图")
        self.thumbnail.setProperty("fluentRole", "subtle")
        self.thumbnail.setFixedSize(300, 169)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_root.addWidget(self.thumbnail, 0, Qt.AlignmentFlag.AlignTop)
        details = QVBoxLayout()
        details.setSpacing(9)
        self.video_title = QLabel()
        self.video_title.setProperty("headingLevel", "2")
        self.video_title.setWordWrap(True)
        details.addWidget(self.video_title)
        self.video_meta = QLabel()
        self.video_meta.setProperty("secondary", True)
        details.addWidget(self.video_meta)
        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("清晰度"))
        self.format_combo = QComboBox()
        self.format_combo.setAccessibleName("下载清晰度")
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        quality_row.addWidget(self.format_combo, 1)
        details.addLayout(quality_row)
        filename_row = QHBoxLayout()
        filename_row.addWidget(QLabel("文件名"))
        self.filename_input = QLineEdit()
        self.filename_input.setAccessibleName("输出文件名")
        filename_row.addWidget(self.filename_input, 1)
        details.addLayout(filename_row)
        directory_row = QHBoxLayout()
        directory_row.addWidget(QLabel("保存到"))
        self.directory_input = QLineEdit(download_directory)
        self.directory_input.setAccessibleName("下载目录")
        self.directory_input.textEdited.connect(self._mark_directory_overridden)
        browse = QPushButton("浏览")
        browse.setToolTip("选择下载文件夹")
        browse.setAccessibleName("浏览下载目录")
        browse.clicked.connect(self._browse_directory)
        directory_row.addWidget(self.directory_input, 1)
        directory_row.addWidget(browse)
        details.addLayout(directory_row)
        self.technical_info = QLabel()
        self.technical_info.setProperty("secondary", True)
        self.technical_info.setWordWrap(True)
        details.addWidget(self.technical_info)
        actions = QHBoxLayout()
        self.download_button = QPushButton("下载")
        self.download_button.setProperty("fluentAppearance", "primary")
        self.download_button.setAccessibleName("将当前视频加入下载队列")
        self.download_button.clicked.connect(self._request_download)
        actions.addStretch()
        actions.addWidget(self.download_button)
        details.addLayout(actions)
        info_root.addLayout(details, 1)
        self.video_card.hide()
        root.addWidget(self.video_card)

        self.tasks_heading = QLabel("下载任务")
        self.tasks_heading.setProperty("headingLevel", "2")
        self.tasks_heading.hide()
        root.addWidget(self.tasks_heading)
        self.task_host = QWidget()
        self.task_layout = QVBoxLayout(self.task_host)
        self.task_layout.setContentsMargins(0, 0, 4, 0)
        self.task_layout.setSpacing(10)
        self.task_layout.addStretch()
        self.task_host.hide()
        root.addWidget(self.task_host)
        root.addStretch()
        self.page_scroll.setWidget(page_host)
        outer.addWidget(self.page_scroll)

    def set_clipboard_hint(self, text: str) -> None:
        try:
            normalized = normalize_youtube_url(text)
        except InvalidYoutubeUrl:
            self.clipboard_hint.hide()
            return
        self.clipboard_hint.setText(f"剪贴板中有可用链接：{normalized}")
        self.clipboard_hint.show()

    def _request_parse(self) -> None:
        if self.url_input.text().strip():
            if self.motion:
                self.motion.feedback(self.parse_button)
            self.parse_requested.emit(self.url_input.text().strip())

    def set_loading(self, loading: bool) -> None:
        if loading:
            self.video = None
            self.video_card.hide()
            self.thumbnail.clear()
            self.thumbnail.setText("暂无封面")
        self.url_input.setEnabled(not loading)
        self.parse_button.setEnabled(not loading)
        self.parse_button.setText("解析中…" if loading else "解析")
        self.metadata_busy.setVisible(loading)

    def show_video(self, video: VideoInfo, *, preferred_quality: str = "recommended") -> None:
        self.video = video
        self._directory_overridden = False
        self.directory_input.setText(self._default_directory)
        self.video_title.setText(video.title)
        self.video_meta.setText(f"{video.channel}  ·  {format_duration(video.duration)}")
        self.thumbnail.clear()
        self.thumbnail.setText("暂无封面")
        pixmap = QPixmap()
        if video.thumbnail_bytes:
            pixmap.loadFromData(video.thumbnail_bytes)
        if not pixmap.isNull():
            self.thumbnail.setPixmap(pixmap.scaled(self.thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        self.format_combo.clear()
        selected = 0
        for index, option in enumerate(video.formats):
            label = f"{option.label}（推荐）" if option.is_recommended else option.label
            self.format_combo.addItem(label, option)
            if (preferred_quality == "recommended" and option.is_recommended) or option.label == preferred_quality:
                selected = index
        self.format_combo.setCurrentIndex(selected)
        self.filename_input.setText(sanitize_filename(video.title))
        self._format_changed()
        if self.motion:
            self.motion.reveal(self.video_card)
        else:
            self.video_card.show()

    def _format_changed(self) -> None:
        option = self.format_combo.currentData()
        if option:
            size = format_bytes(option.estimated_size)
            if option.estimated_size is None:
                size_text = "大小未知"
            elif option.size_is_estimate:
                size_text = f"估算 {size}"
            else:
                size_text = f"大小 {size}"
            self.technical_info.setText(f"{option.technical_summary}  ·  {size_text}")

    def _browse_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择下载目录", self.directory_input.text())
        if selected:
            self._directory_overridden = True
            self.directory_input.setText(selected)

    def _mark_directory_overridden(self, _text: str) -> None:
        self._directory_overridden = True

    def set_default_directory(self, directory: str) -> None:
        self._default_directory = directory
        if self.video is None or not self._directory_overridden:
            self.directory_input.setText(directory)

    def _request_download(self) -> None:
        option = self.format_combo.currentData()
        if self.video and option:
            if self.motion:
                self.motion.feedback(self.download_button)
            self.download_requested.emit(self.video, option, self.filename_input.text(), self.directory_input.text())

    def add_task(self, request: DownloadRequest) -> None:
        card = DownloadTaskCard(request)
        card.cancel_requested.connect(self.cancel_requested)
        card.open_file_requested.connect(self.open_file_requested)
        card.open_folder_requested.connect(self.open_folder_requested)
        self.cards[request.task_id] = card
        self.task_layout.insertWidget(self.task_layout.count() - 1, card)
        self.tasks_heading.show()
        self.task_host.show()
        if self.motion:
            self.motion.reveal(card)

    def update_task(self, progress: DownloadProgress) -> None:
        card = self.cards.get(progress.task_id)
        if card:
            card.update_progress(progress)

    def cancel_task(self, task_id: str) -> None:
        card = self.cards.get(task_id)
        if card:
            card.set_cancelling()

    def complete_task(self, result: DownloadResult) -> None:
        card = self.cards.get(result.task_id)
        if card:
            card.set_completed(result)
            self._mark_terminal(result.task_id)

    def fail_task(
        self,
        task_id: str,
        status: TaskStatus,
        cleanup_report: CancellationCleanupReport | None = None,
    ) -> None:
        card = self.cards.get(task_id)
        if card:
            card.set_terminal_status(status, cleanup_report)
            self._mark_terminal(task_id)

    def _mark_terminal(self, task_id: str) -> None:
        for previous_id in tuple(self._terminal_task_ids):
            if previous_id != task_id:
                self._remove_task(previous_id)
        self._terminal_task_ids.add(task_id)

    def task_started(self, task_id: str) -> None:
        for terminal_id in tuple(self._terminal_task_ids):
            if terminal_id != task_id:
                self._remove_task(terminal_id)

    def _remove_task(self, task_id: str) -> None:
        card = self.cards.pop(task_id, None)
        self._terminal_task_ids.discard(task_id)
        if card:
            self.task_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        if not self.cards:
            self.tasks_heading.hide()
            self.task_host.hide()

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from yt_downloader.core.models import AppSettings


class SettingsPage(QWidget):
    save_requested = Signal(object)
    theme_preview_requested = Signal(str)
    open_logs_requested = Signal()
    copy_system_info_requested = Signal()

    def __init__(self, settings: AppSettings, *, ytdlp_version: str, ffmpeg_description: str, parent=None) -> None:
        super().__init__(parent)
        self._saved = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)
        heading = QLabel("设置")
        heading.setProperty("headingLevel", "1")
        root.addWidget(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        content = QVBoxLayout(host)
        content.setContentsMargins(0, 0, 12, 12)
        content.setSpacing(14)

        content.addWidget(self._section("下载"))
        download_card = QWidget()
        download_card.setProperty("fluentRole", "card")
        form = QFormLayout(download_card)
        form.setContentsMargins(18, 16, 18, 16)
        self.directory_input = QLineEdit(settings.download_directory)
        browse = QPushButton("浏览")
        browse.clicked.connect(self._browse_download)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.directory_input, 1)
        row_layout.addWidget(browse)
        form.addRow("默认下载目录", row)
        self.quality_combo = QComboBox()
        for label, value in (("自动推荐", "recommended"), ("2160p", "2160p 4K"), ("1440p", "1440p 2K"), ("1080p", "1080p"), ("720p", "720p")):
            self.quality_combo.addItem(label, value)
        index = self.quality_combo.findData(settings.default_quality)
        self.quality_combo.setCurrentIndex(max(0, index))
        form.addRow("默认画质", self.quality_combo)
        content.addWidget(download_card)

        content.addWidget(self._section("外观"))
        appearance = QWidget()
        appearance.setProperty("fluentRole", "card")
        appearance_form = QFormLayout(appearance)
        appearance_form.setContentsMargins(18, 16, 18, 16)
        self.theme_combo = QComboBox()
        for label, value in (("跟随系统", "system"), ("浅色", "light"), ("深色", "dark")):
            self.theme_combo.addItem(label, value)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(settings.theme)))
        self.reduce_motion = QCheckBox("减少界面动态效果")
        self.reduce_motion.setChecked(settings.reduce_motion)
        appearance_form.addRow("主题", self.theme_combo)
        appearance_form.addRow("", self.reduce_motion)
        content.addWidget(appearance)

        content.addWidget(self._section("工具与诊断"))
        tools = QWidget()
        tools.setProperty("fluentRole", "card")
        tools_form = QFormLayout(tools)
        tools_form.setContentsMargins(18, 16, 18, 16)
        tools_form.addRow("yt-dlp", QLabel(ytdlp_version))
        tools_form.addRow("FFmpeg", QLabel(ffmpeg_description))
        self.ffmpeg_input = QLineEdit(settings.ffmpeg_directory)
        self.ffmpeg_input.setPlaceholderText("留空时使用随软件分发的 FFmpeg")
        repair = QPushButton("修复路径")
        repair.clicked.connect(self._browse_ffmpeg)
        ffrow = QWidget()
        fflayout = QHBoxLayout(ffrow)
        fflayout.setContentsMargins(0, 0, 0, 0)
        fflayout.addWidget(self.ffmpeg_input, 1)
        fflayout.addWidget(repair)
        tools_form.addRow("FFmpeg 目录", ffrow)
        diagnostics = QWidget()
        diagnostic_layout = QHBoxLayout(diagnostics)
        diagnostic_layout.setContentsMargins(0, 0, 0, 0)
        logs = QPushButton("打开日志目录")
        logs.clicked.connect(self.open_logs_requested)
        copy = QPushButton("复制系统信息")
        copy.clicked.connect(self.copy_system_info_requested)
        diagnostic_layout.addWidget(logs)
        diagnostic_layout.addWidget(copy)
        diagnostic_layout.addStretch()
        tools_form.addRow("诊断", diagnostics)
        content.addWidget(tools)
        content.addStretch()
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        self.save_bar = QWidget()
        self.save_bar.setProperty("fluentRole", "card")
        save_layout = QHBoxLayout(self.save_bar)
        save_layout.setContentsMargins(14, 10, 14, 10)
        self.unsaved_label = QLabel("有未保存的更改")
        self.unsaved_label.setProperty("secondary", True)
        self.save_button = QPushButton("保存设置")
        self.save_button.setProperty("fluentAppearance", "primary")
        self.save_button.clicked.connect(self._save)
        save_layout.addWidget(self.unsaved_label)
        save_layout.addStretch()
        save_layout.addWidget(self.save_button)
        self.save_bar.hide()
        root.addWidget(self.save_bar)

        self.directory_input.textChanged.connect(self._mark_dirty)
        self.quality_combo.currentIndexChanged.connect(self._mark_dirty)
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        self.reduce_motion.toggled.connect(self._mark_dirty)
        self.ffmpeg_input.textChanged.connect(self._mark_dirty)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("headingLevel", "2")
        return label

    def _browse_download(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择默认下载目录", self.directory_input.text())
        if path:
            self.directory_input.setText(path)

    def _browse_ffmpeg(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择包含 ffmpeg.exe 和 ffprobe.exe 的目录", self.ffmpeg_input.text())
        if path:
            self.ffmpeg_input.setText(path)

    def _theme_changed(self) -> None:
        self._mark_dirty()
        self.theme_preview_requested.emit(str(self.theme_combo.currentData()))

    def _mark_dirty(self, *_args) -> None:
        self.save_bar.show()

    def current_settings(self) -> AppSettings:
        return AppSettings(
            schema_version=1,
            download_directory=self.directory_input.text().strip(),
            default_quality=str(self.quality_combo.currentData()),
            theme=str(self.theme_combo.currentData()),
            reduce_motion=self.reduce_motion.isChecked(),
            ffmpeg_directory=self.ffmpeg_input.text().strip(),
        )

    def _save(self) -> None:
        self.save_requested.emit(self.current_settings())

    def mark_saved(self, settings: AppSettings) -> None:
        self._saved = settings
        self.save_bar.hide()


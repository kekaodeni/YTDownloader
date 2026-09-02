from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from yt_downloader.core.models import AppSettings
from yt_downloader.ui.typography import (
    FontRole,
    apply_form_typography,
    apply_typography,
    apply_typography_tree,
)


class SettingsPage(QWidget):
    save_requested = Signal(object)
    network_test_requested = Signal(str, str)
    theme_preview_requested = Signal(str)
    open_logs_requested = Signal()
    copy_system_info_requested = Signal()

    def __init__(self, settings: AppSettings, *, ytdlp_version: str, ffmpeg_description: str, parent=None) -> None:
        super().__init__(parent)
        self._saved = settings
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self._save)
        self._status_hide_timer = QTimer(self)
        self._status_hide_timer.setSingleShot(True)
        self._status_hide_timer.setInterval(1800)
        self._status_hide_timer.timeout.connect(lambda: self.save_bar.hide())
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)
        heading = QLabel("设置")
        apply_typography(heading, FontRole.PAGE_TITLE)
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
        self.fragments_combo = QComboBox()
        for label, value in (("自动", 0), ("1", 1), ("2", 2), ("4", 4), ("8", 8)):
            self.fragments_combo.addItem(label, value)
        self.fragments_combo.setCurrentIndex(max(0, self.fragments_combo.findData(settings.concurrent_fragments)))
        self.fragments_combo.setAccessibleName("分片并发数")
        self.fragments_combo.setToolTip("自动模式使用实测确认的稳健并发数；分片并发只对支持分片的格式有效。")
        form.addRow("分片并发", self.fragments_combo)

        self.proxy_combo = QComboBox()
        for label, value in (("系统代理", "system"), ("直连", "direct"), ("自定义代理", "custom")):
            self.proxy_combo.addItem(label, value)
        self.proxy_combo.setCurrentIndex(max(0, self.proxy_combo.findData(settings.proxy_mode)))
        self.proxy_combo.setAccessibleName("网络代理模式")
        form.addRow("网络连接", self.proxy_combo)
        self.proxy_input = QLineEdit(settings.custom_proxy_url)
        self.proxy_input.setPlaceholderText("例如 http://127.0.0.1:8080 或 socks5://127.0.0.1:1080")
        self.proxy_input.setAccessibleName("自定义代理地址")
        self.proxy_input.setToolTip("支持 HTTP、HTTPS、SOCKS4、SOCKS5 和 SOCKS5H；日志不会记录用户名或密码。")
        form.addRow("自定义代理", self.proxy_input)
        network_test_row = QWidget()
        network_test_layout = QHBoxLayout(network_test_row)
        network_test_layout.setContentsMargins(0, 0, 0, 0)
        self.network_test_button = QPushButton("测试连接")
        self.network_test_button.setAccessibleName("测试当前网络连接")
        self.network_test_button.setToolTip("使用当前代理选项连接 YouTube；不会保存设置。")
        self.network_test_button.clicked.connect(self._request_network_test)
        self.network_test_status = QLabel("")
        apply_typography(self.network_test_status, FontRole.CAPTION)
        self.network_test_status.setWordWrap(True)
        network_test_layout.addWidget(self.network_test_button)
        network_test_layout.addWidget(self.network_test_status, 1)
        form.addRow("连接诊断", network_test_row)
        self._update_proxy_controls()
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
        apply_typography(self.unsaved_label, FontRole.SECONDARY)
        self.save_button = QPushButton("立即保存")
        self.save_button.setProperty("fluentAppearance", "primary")
        self.save_button.clicked.connect(self._save)
        save_layout.addWidget(self.unsaved_label)
        save_layout.addStretch()
        save_layout.addWidget(self.save_button)
        self.save_bar.hide()
        root.addWidget(self.save_bar)

        self.directory_input.textChanged.connect(self._mark_dirty)
        self.quality_combo.currentIndexChanged.connect(self._mark_dirty_immediately)
        self.fragments_combo.currentIndexChanged.connect(self._mark_dirty_immediately)
        self.proxy_combo.currentIndexChanged.connect(self._proxy_changed)
        self.proxy_input.textChanged.connect(self._mark_dirty)
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        self.reduce_motion.toggled.connect(self._mark_dirty_immediately)
        self.ffmpeg_input.textChanged.connect(self._mark_dirty)
        for current_form in (form, appearance_form, tools_form):
            apply_form_typography(current_form)
        apply_typography_tree(self)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        apply_typography(label, FontRole.SECTION_TITLE)
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
        self._mark_dirty_immediately()
        self.theme_preview_requested.emit(str(self.theme_combo.currentData()))

    def _proxy_changed(self) -> None:
        self._update_proxy_controls()
        self.network_test_status.clear()
        self._mark_dirty_immediately()

    def _update_proxy_controls(self) -> None:
        self.proxy_input.setEnabled(self.proxy_combo.currentData() == "custom")

    def _request_network_test(self) -> None:
        self.set_network_test_busy(True)
        self.network_test_requested.emit(
            str(self.proxy_combo.currentData()),
            self.proxy_input.text().strip(),
        )

    def set_network_test_busy(self, busy: bool) -> None:
        self.network_test_button.setEnabled(not busy)
        self.network_test_button.setText("正在测试…" if busy else "测试连接")
        if busy:
            self.network_test_status.setText("正在使用当前设置测试连接…")

    def set_network_test_result(self, success: bool, message: str) -> None:
        self.set_network_test_busy(False)
        self.network_test_status.setProperty("status", "success" if success else "error")
        self.network_test_status.setText(message)
        self.network_test_status.style().unpolish(self.network_test_status)
        self.network_test_status.style().polish(self.network_test_status)

    def _mark_dirty(self, *_args) -> None:
        self._status_hide_timer.stop()
        self.unsaved_label.setText("有未保存的更改")
        self.save_bar.show()
        self._autosave_timer.start(500)

    def _mark_dirty_immediately(self, *_args) -> None:
        self._mark_dirty()
        self._autosave_timer.start(0)

    def current_settings(self) -> AppSettings:
        return AppSettings(
            schema_version=2,
            download_directory=self.directory_input.text().strip(),
            default_quality=str(self.quality_combo.currentData()),
            theme=str(self.theme_combo.currentData()),
            reduce_motion=self.reduce_motion.isChecked(),
            ffmpeg_directory=self.ffmpeg_input.text().strip(),
            proxy_mode=str(self.proxy_combo.currentData()),
            custom_proxy_url=self.proxy_input.text().strip(),
            concurrent_fragments=int(self.fragments_combo.currentData()),
        )

    def _save(self) -> None:
        self._autosave_timer.stop()
        self._status_hide_timer.stop()
        self.unsaved_label.setText("正在保存…")
        self.save_bar.show()
        self.save_requested.emit(self.current_settings())

    def mark_saved(self, settings: AppSettings) -> None:
        self._saved = settings
        self.unsaved_label.setText("已保存")
        self.save_bar.show()
        self._status_hide_timer.start()

    def mark_save_failed(self, message: str) -> None:
        self._status_hide_timer.stop()
        self.unsaved_label.setText(f"无法保存：{message}")
        self.save_bar.show()

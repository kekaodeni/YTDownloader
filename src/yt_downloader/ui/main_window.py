from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from yt_downloader.core.models import AppSettings
from yt_downloader.ui.icons import FluentIconService
from yt_downloader.ui.motion import MotionManager
from yt_downloader.ui.smooth_scroll import SmoothScrollController
from yt_downloader.ui.diagnostics import ReducedMotionPolicy, UIAnimationDiagnostics
from yt_downloader.ui.pages.about_page import AboutPage
from yt_downloader.ui.pages.download_page import DownloadPage
from yt_downloader.ui.pages.history_page import HistoryPage
from yt_downloader.ui.pages.settings_page import SettingsPage
from yt_downloader.ui.typography import apply_typography_tree
from yt_downloader.infrastructure.runtime import resource_path


class MainWindow(QMainWindow):
    cancel_all_requested = Signal()
    cancel_update_requested = Signal()
    show_update_requested = Signal()

    def __init__(
        self,
        settings: AppSettings,
        *,
        ytdlp_version: str,
        ffmpeg_description: str,
        icons: FluentIconService | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("YT Downloader")
        self.setWindowIcon(QIcon(str(resource_path("assets", "app.ico"))))
        self.resize(1100, 720)
        self.setMinimumSize(820, 560)
        self._busy = False
        self._update_busy = False
        self._closing_after_cancel = False
        self.icons = icons or FluentIconService()
        self.motion = MotionManager(settings.reduce_motion, self)
        self.reduced_motion_policy = ReducedMotionPolicy(settings.reduce_motion, self)
        self.reduced_motion_policy.changed.connect(self.motion.set_reduce_motion)
        shell = QWidget()
        self.setCentralWidget(shell)
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.navigation = QWidget()
        self.navigation.setObjectName("navigationRail")
        self.navigation.setFixedWidth(184)
        nav = QVBoxLayout(self.navigation)
        nav.setContentsMargins(10, 18, 10, 12)
        nav.setSpacing(6)
        self.stack = QStackedWidget()
        self.download_page = DownloadPage(settings.download_directory, motion=self.motion)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(settings, ytdlp_version=ytdlp_version, ffmpeg_description=ffmpeg_description)
        self.about_page = AboutPage()
        for page in (self.download_page, self.history_page, self.settings_page, self.about_page):
            self.stack.addWidget(page)
        self.smooth_scroll = SmoothScrollController(self.motion, self)
        for area in (self.download_page.page_scroll, self.history_page.list_view, self.settings_page.page_scroll):
            self.smooth_scroll.install(area)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QToolButton] = []
        specs = (
            ("下载", "arrow_download", 0),
            ("历史记录", "history", 1),
            ("设置", "settings", 2),
        )
        for label, icon, index in specs:
            button = self._nav_button(label, icon, index)
            nav.addWidget(button)
        nav.addStretch()
        nav.addWidget(self._nav_button("关于", "info", 3))
        layout.addWidget(self.navigation)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.update_banner = QWidget()
        self.update_banner.setProperty("fluentRole", "card")
        banner_layout = QHBoxLayout(self.update_banner)
        banner_layout.setContentsMargins(18, 8, 18, 8)
        self.update_banner_label = QLabel()
        self.update_banner_open = QPushButton("查看更新")
        self.update_banner_close = QPushButton("关闭")
        self.update_banner_open.clicked.connect(self.show_update_requested)
        self.update_banner_close.clicked.connect(self.update_banner.hide)
        banner_layout.addWidget(self.update_banner_label, 1)
        banner_layout.addWidget(self.update_banner_open)
        banner_layout.addWidget(self.update_banner_close)
        self.update_banner.hide()
        right_layout.addWidget(self.update_banner)
        right_layout.addWidget(self.stack, 1)
        layout.addWidget(right, 1)
        self.nav_buttons[0].setChecked(True)
        self._select_page(0)
        apply_typography_tree(self)

    def _nav_button(self, label: str, icon_name: str, index: int) -> QToolButton:
        button = QToolButton()
        button.setText(label)
        button.setProperty("iconName", icon_name)
        button.setIcon(self.icons.icon(icon_name))
        button.setIconSize(QSize(20, 20))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(True)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setMinimumHeight(42)
        button.clicked.connect(lambda _checked=False, value=index: self._select_page(value))
        self.nav_group.addButton(button, index)
        self.nav_buttons.append(button)
        return button

    def _select_page(self, index: int) -> None:
        self.motion.switch_page(self.stack, index)
        for button_index, button in enumerate(self.nav_buttons):
            selected = button_index == index
            button.setChecked(selected)
            button.setProperty("navSelected", selected)
            button.setIcon(self.icons.icon(str(button.property("iconName")), selected=selected))
            button.style().unpolish(button)
            button.style().polish(button)

    def apply_theme(self, theme: str) -> None:
        for button in self.nav_buttons:
            button.setIcon(
                self.icons.icon(
                    str(button.property("iconName")),
                    selected=button.isChecked(),
                    theme=theme,
                )
            )
        self.download_page.apply_theme(theme)

    def show_update_available(self, version: str) -> None:
        self.update_banner_label.setText(f"YT Downloader {version} 已可用")
        self.update_banner.show()

    def set_download_busy(self, busy: bool) -> None:
        self._busy = busy
        if not busy and not self._update_busy and self._closing_after_cancel:
            self._closing_after_cancel = False
            self.close()

    def set_update_busy(self, busy: bool) -> None:
        self._update_busy = busy
        if not busy and not self._busy and self._closing_after_cancel:
            self._closing_after_cancel = False
            self.close()

    def set_reduce_motion(self, enabled: bool) -> None:
        self.reduced_motion_policy.set_enabled(enabled)

    def create_animation_diagnostics(self) -> UIAnimationDiagnostics:
        diagnostics = UIAnimationDiagnostics(self)
        diagnostics.register_active_provider(lambda: self.motion.active_count)
        diagnostics.register_active_provider(lambda: self.smooth_scroll.active_count)
        return diagnostics

    def resizeEvent(self, event) -> None:
        compact = self.width() < 900
        self.navigation.setFixedWidth(64 if compact else 184)
        for button in self.nav_buttons:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if compact else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._busy and not self._update_busy:
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle("后台任务仍在进行")
        box.setText("仍有下载或更新任务。你可以继续等待，或取消任务后退出。")
        wait_button = box.addButton("继续等待", QMessageBox.ButtonRole.RejectRole)
        cancel_button = box.addButton("取消任务并退出", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(wait_button)
        box.exec()
        if box.clickedButton() is cancel_button:
            self._closing_after_cancel = True
            if self._busy:
                self.cancel_all_requested.emit()
            if self._update_busy:
                self.cancel_update_requested.emit()
            self.hide()
        event.ignore()

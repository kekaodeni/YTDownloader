from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from yt_downloader.core.models import AppSettings
from yt_downloader.ui.icons import FluentIconService
from yt_downloader.ui.pages.about_page import AboutPage
from yt_downloader.ui.pages.download_page import DownloadPage
from yt_downloader.ui.pages.history_page import HistoryPage
from yt_downloader.ui.pages.settings_page import SettingsPage
from yt_downloader.infrastructure.runtime import resource_path


class MainWindow(QMainWindow):
    cancel_all_requested = Signal()

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
        self._closing_after_cancel = False
        self.icons = icons or FluentIconService()
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
        self.download_page = DownloadPage(settings.download_directory)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(settings, ytdlp_version=ytdlp_version, ffmpeg_description=ffmpeg_description)
        self.about_page = AboutPage()
        for page in (self.download_page, self.history_page, self.settings_page, self.about_page):
            self.stack.addWidget(page)
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
        layout.addWidget(self.stack, 1)
        self.nav_buttons[0].setChecked(True)
        self._select_page(0)

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
        self.stack.setCurrentIndex(index)
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

    def set_download_busy(self, busy: bool) -> None:
        self._busy = busy
        if not busy and self._closing_after_cancel:
            self._closing_after_cancel = False
            self.close()

    def resizeEvent(self, event) -> None:
        compact = self.width() < 900
        self.navigation.setFixedWidth(64 if compact else 184)
        for button in self.nav_buttons:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if compact else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._busy:
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle("下载仍在进行")
        box.setText("仍有下载任务。你可以继续等待，或取消任务后退出。")
        wait_button = box.addButton("继续等待", QMessageBox.ButtonRole.RejectRole)
        cancel_button = box.addButton("取消任务并退出", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(wait_button)
        box.exec()
        if box.clickedButton() is cancel_button:
            self._closing_after_cancel = True
            self.cancel_all_requested.emit()
            self.hide()
        event.ignore()

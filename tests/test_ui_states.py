from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import QPushButton

from yt_downloader.core.errors import AppError
from yt_downloader.core.models import AppSettings
from yt_downloader.ui.pages.download_page import DownloadPage
from yt_downloader.ui.icons import FluentIconService
from yt_downloader.ui.theme import ThemeManager
from yt_downloader.ui.widgets.error_dialog import ErrorDialog
from test_download_service import _request
from yt_downloader.core.models import DownloadProgress, TaskStatus


def test_metadata_busy_state_disables_input_without_blocking(qtbot, tmp_path) -> None:
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    page.show()
    page.set_loading(True)
    assert page.metadata_busy.isVisible()
    assert not page.url_input.isEnabled()
    assert not page.parse_button.isEnabled()
    assert page.metadata_busy.maximum() == 0
    page.set_loading(False)
    assert page.url_input.isEnabled()
    assert page.parse_button.isEnabled()


def test_theme_manager_updates_qpalette(qapp) -> None:
    manager = ThemeManager(qapp)
    manager.set_mode("dark")
    assert manager.resolved_mode == "dark"
    assert qapp.palette().color(QPalette.ColorRole.Window).lightness() < 80
    manager.set_mode("light")
    assert qapp.palette().color(QPalette.ColorRole.Window).lightness() > 200


def test_fluent_icons_use_theme_contrast_and_selected_variant(qapp) -> None:
    icons = FluentIconService()
    regular = icons.icon("history", theme="dark")
    selected = icons.icon("history", selected=True, theme="dark")

    image = regular.pixmap(24, 24).toImage()
    visible = [
        image.pixelColor(x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    ]
    assert visible
    assert max(color.lightness() for color in visible) >= 180
    assert regular.cacheKey() != selected.cacheKey()


def test_error_dialog_copies_prebuilt_redacted_report(qtbot) -> None:
    dialog = ErrorDialog(AppError("x", "用户说明", "技术详情"), "safe report")
    qtbot.addWidget(dialog)
    copy = next(button for button in dialog.findChildren(QPushButton) if button.text() == "复制错误报告")
    qtbot.mouseClick(copy, Qt.MouseButton.LeftButton)
    assert QGuiApplication.clipboard().text() == "safe report"


def test_task_card_enters_cancelling_immediately(qtbot, tmp_path) -> None:
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    request = replace(_request(tmp_path), task_id="cancel-ui")
    page.add_task(request)
    page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 31, 31, 100, 5000, 7))

    page.cancel_task(request.task_id)

    card = page.cards[request.task_id]
    assert card.progress.status_label.text() == "正在取消…"
    assert not card.cancel_button.isEnabled()
    assert card.cancel_button.text() == "正在取消…"
    assert card.progress.progress_bar.maximum() == 100
    assert card.progress.speed_label.text() == "—"
    assert card.progress.eta_label.text() == "剩余 —"

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QPalette, QPixmap
from PySide6.QtWidgets import QPushButton

from yt_downloader.core.errors import AppError
from yt_downloader.core.models import AppSettings
from yt_downloader.ui.pages.download_page import DownloadPage
from yt_downloader.ui.pages.settings_page import SettingsPage
from yt_downloader.ui.icons import FluentIconService
from yt_downloader.ui.theme import ThemeManager
from yt_downloader.ui.widgets.error_dialog import ErrorDialog
from test_download_service import _request
from yt_downloader.core.models import DownloadProgress, DownloadResult, TaskStatus


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


def test_new_metadata_clears_the_previous_thumbnail_when_image_is_missing(qtbot, tmp_path) -> None:
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    source = _request(tmp_path).video
    image = QPixmap(4, 4)
    image.fill(Qt.GlobalColor.blue)
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    png = bytes(encoded)
    first = replace(source, video_id="first-video", title="A", thumbnail_bytes=png)
    second = replace(source, video_id="second-video", title="B", thumbnail_bytes=None)

    page.show_video(first)
    assert not page.thumbnail.pixmap().isNull()

    page.show_video(second)

    assert page.thumbnail.pixmap().isNull()
    assert page.thumbnail.text() == "暂无封面"


def test_starting_the_next_task_retires_older_terminal_cards(qtbot, tmp_path) -> None:
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    first = replace(_request(tmp_path), task_id="first")
    second = replace(_request(tmp_path), task_id="second")
    page.add_task(first)
    page.add_task(second)
    page.complete_task(DownloadResult("first", tmp_path / "first.mp4", 10, "now"))

    assert set(page.cards) == {"first", "second"}

    page.task_started("second")

    assert set(page.cards) == {"second"}


def test_settings_auto_save_after_text_edit_and_show_saved_status(qtbot, tmp_path) -> None:
    page = SettingsPage(
        AppSettings(download_directory=str(tmp_path)),
        ytdlp_version="test",
        ffmpeg_description="test",
    )
    qtbot.addWidget(page)
    changed = tmp_path / "新的默认目录"

    with qtbot.waitSignal(page.save_requested, timeout=1500) as signal:
        page.directory_input.setText(str(changed))

    saved = signal.args[0]
    assert saved.schema_version == 2
    assert saved.download_directory == str(changed)
    assert page.unsaved_label.text() == "正在保存…"

    page.mark_saved(saved)

    assert page.unsaved_label.text() == "已保存"


def test_saved_default_directory_applies_to_new_videos_without_overwriting_manual_choice(qtbot, tmp_path) -> None:
    first_default = str(tmp_path / "first-default")
    second_default = str(tmp_path / "second-default")
    manual = str(tmp_path / "manual-for-current-video")
    page = DownloadPage(first_default)
    qtbot.addWidget(page)
    source = _request(tmp_path).video
    page.show_video(source)

    page.set_default_directory(second_default)
    assert page.directory_input.text() == second_default

    page.directory_input.setText(manual)
    page.directory_input.textEdited.emit(manual)
    page.set_default_directory(str(tmp_path / "third-default"))
    assert page.directory_input.text() == manual

    page.show_video(replace(source, video_id="next-video"))
    assert page.directory_input.text() == str(tmp_path / "third-default")

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QFont, QGuiApplication, QPalette, QPixmap
from PySide6.QtWidgets import QPushButton, QSizePolicy, QToolButton

from yt_downloader.core.errors import AppError, CancellationCleanupReport
from yt_downloader.core.models import AppSettings, CodecPreference
from yt_downloader.ui.pages.download_page import DownloadPage
from yt_downloader.ui.pages.settings_page import SettingsPage
from yt_downloader.ui.icons import FluentIconService
from yt_downloader.ui.motion import MotionManager
from yt_downloader.ui.theme import DARK, LIGHT, ThemeManager, _qss
from yt_downloader.ui.typography import FontRole
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


def test_metadata_busy_label_is_never_clipped_by_feedback_motion(
    qapp,
    qtbot,
    tmp_path,
) -> None:
    theme = ThemeManager(qapp)
    theme.set_mode("light")
    motion = MotionManager(reduce_motion=False)
    page = DownloadPage(str(tmp_path), motion=motion)
    qtbot.addWidget(page)
    page.resize(1100, 720)
    page.show()
    page.url_input.setText("https://youtu.be/dQw4w9WgXcQ")
    page.parse_requested.connect(lambda _url: page.set_loading(True))

    page.parse_button.click()

    for delay in (0, 80, 120):
        if delay:
            qtbot.wait(delay)
        qapp.processEvents()
        assert page.parse_button.text().startswith("解析中")
        assert page.parse_button.width() >= page.parse_button.sizeHint().width()
        assert page.parse_button.width() >= 80


def test_url_clear_action_is_vertically_centered_by_qt_layout(qapp, qtbot, tmp_path) -> None:
    manager = ThemeManager(qapp)
    manager.set_mode("light")
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    page.resize(1100, 720)
    page.show()
    page.url_input.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    qapp.processEvents()
    clear_button = page.url_input.findChild(QToolButton)

    assert clear_button is not None
    assert abs(
        clear_button.geometry().center().y()
        - page.url_input.rect().center().y()
    ) <= 1


def test_theme_manager_updates_qpalette(qapp) -> None:
    manager = ThemeManager(qapp)
    manager.set_mode("dark")
    assert manager.resolved_mode == "dark"
    assert qapp.palette().color(QPalette.ColorRole.Window).lightness() < 80
    manager.set_mode("light")
    assert qapp.palette().color(QPalette.ColorRole.Window).lightness() > 200


def _contrast_ratio(first, second) -> float:
    def luminance(color) -> float:
        channels = []
        for value in (color.redF(), color.greenF(), color.blueF()):
            channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_combo_selection_palette_remains_readable_in_both_themes(qapp) -> None:
    manager = ThemeManager(qapp)
    for mode, tokens in (("light", LIGHT), ("dark", DARK)):
        manager.set_mode(mode)
        palette = qapp.palette()
        selected_background = palette.color(QPalette.ColorRole.Highlight)
        selected_text = palette.color(QPalette.ColorRole.HighlightedText)

        assert selected_background.name().upper() == tokens.selection.upper()
        assert selected_text.name().upper() == tokens.text.upper()
        assert _contrast_ratio(selected_background, selected_text) >= 4.5


def test_generated_qss_covers_combo_selected_hover_focus_and_disabled_states() -> None:
    stylesheet = _qss(LIGHT)

    assert "QComboBox QAbstractItemView::item:selected:hover" in stylesheet
    assert "QComboBox QAbstractItemView:focus" in stylesheet
    assert "QComboBox QAbstractItemView::item:disabled" in stylesheet
    assert f"selection-color: {LIGHT.text}" in stylesheet


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


def test_cancel_cleanup_warning_offers_the_output_folder(qtbot, tmp_path) -> None:
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    page.show()
    request = replace(_request(tmp_path), task_id="cancel-cleanup-warning")
    page.add_task(request)
    report = CancellationCleanupReport(
        task_id=request.task_id,
        output_directory=str(tmp_path),
        failed_paths=(str(tmp_path / ".ytdownloader-tmp" / "task-owned"),),
        errors=("locked",),
    )

    page.fail_task(request.task_id, TaskStatus.CANCELLED, report)

    card = page.cards[request.task_id]
    assert card.progress.status_label.text() == "已取消，但部分临时文件未能清理"
    assert card.folder_button.isVisible()
    with qtbot.waitSignal(page.open_folder_requested, timeout=500) as signal:
        card.folder_button.click()
    assert signal.args == [str(tmp_path)]


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


def test_dynamic_video_title_keeps_the_card_title_role(qtbot, tmp_path) -> None:
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    source = _request(tmp_path).video

    page.show_video(replace(source, title="桜のテスト動画"))

    assert page.video_title.property("typographyRole") == FontRole.CARD_TITLE.value
    assert page.video_title.font().pointSizeF() == 12.0
    assert page.video_title.font().weight() == QFont.Weight.DemiBold


def test_wrapped_video_text_is_not_squeezed_below_its_required_height(qapp, qtbot, tmp_path) -> None:
    page = DownloadPage(str(tmp_path))
    qtbot.addWidget(page)
    page.resize(640, 560)
    page.show_video(replace(
        _request(tmp_path).video,
        title="Windows 11 Fluent Design：从构想到成品",
    ))
    page.show()
    qapp.processEvents()

    for label in (page.video_title, page.technical_info):
        assert label.sizePolicy().verticalPolicy() is QSizePolicy.Policy.Minimum
        assert label.height() >= label.heightForWidth(label.width())


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


def test_task_replacement_motion_collapses_old_card_without_position_rebound(
    qapp,
    qtbot,
    tmp_path,
) -> None:
    motion = MotionManager(reduce_motion=False)
    page = DownloadPage(str(tmp_path), motion=motion)
    qtbot.addWidget(page)
    page.resize(1100, 720)
    page.show()
    first = replace(_request(tmp_path), task_id="first-motion")
    second = replace(_request(tmp_path), task_id="second-motion")
    page.add_task(first)
    qtbot.waitUntil(lambda: motion.active_count == 0, timeout=1000)
    page.complete_task(DownloadResult(first.task_id, tmp_path / "first.mp4", 10, "now"))
    page.add_task(second)
    qapp.processEvents()

    page.task_started(second.task_id)
    qapp.processEvents()

    assert first.task_id in page.cards
    positions = []
    for _ in range(8):
        positions.append(page.cards[second.task_id].geometry().top())
        qtbot.wait(35)
        qapp.processEvents()

    qtbot.waitUntil(lambda: motion.active_count == 0, timeout=1000)
    assert set(page.cards) == {second.task_id}
    assert all(current <= previous for previous, current in zip(positions, positions[1:]))


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
    assert saved.schema_version == 3
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


def test_network_settings_round_trip_through_auto_save(qtbot, tmp_path) -> None:
    page = SettingsPage(
        AppSettings(
            download_directory=str(tmp_path),
            proxy_mode="custom",
            custom_proxy_url="http://127.0.0.1:8080",
            concurrent_fragments=4,
        ),
        ytdlp_version="test",
        ffmpeg_description="test",
    )
    qtbot.addWidget(page)

    assert page.proxy_combo.currentData() == "custom"
    assert page.proxy_input.text() == "http://127.0.0.1:8080"
    assert page.fragments_combo.currentData() == 4
    assert page.proxy_input.isEnabled()

    with qtbot.waitSignal(page.save_requested, timeout=1000) as signal:
        page.proxy_combo.setCurrentIndex(page.proxy_combo.findData("direct"))

    changed = signal.args[0]
    assert changed.proxy_mode == "direct"
    assert changed.concurrent_fragments == 4
    assert not page.proxy_input.isEnabled()


def test_codec_preference_is_an_advanced_auto_saved_setting(qtbot, tmp_path) -> None:
    page = SettingsPage(
        AppSettings(
            download_directory=str(tmp_path),
            codec_preference=CodecPreference.VP9,
        ),
        ytdlp_version="test",
        ffmpeg_description="test",
    )
    qtbot.addWidget(page)

    assert page.codec_combo.currentData() == CodecPreference.VP9.value
    with qtbot.waitSignal(page.save_requested, timeout=1000) as signal:
        page.codec_combo.setCurrentIndex(
            page.codec_combo.findData(CodecPreference.AV1.value),
        )

    assert signal.args[0].codec_preference is CodecPreference.AV1


def test_network_test_is_separate_from_save_and_has_inline_result(qtbot, tmp_path) -> None:
    page = SettingsPage(
        AppSettings(download_directory=str(tmp_path), proxy_mode="direct"),
        ytdlp_version="test",
        ffmpeg_description="test",
    )
    qtbot.addWidget(page)

    with qtbot.waitSignal(page.network_test_requested, timeout=500) as signal:
        qtbot.mouseClick(page.network_test_button, Qt.MouseButton.LeftButton)

    assert signal.args == ["direct", ""]
    assert not page.network_test_button.isEnabled()
    assert page.network_test_button.text() == "正在测试…"

    page.set_network_test_result(True, "连接成功（0.25 秒） · 直连")

    assert page.network_test_button.isEnabled()
    assert page.network_test_status.text().startswith("连接成功")

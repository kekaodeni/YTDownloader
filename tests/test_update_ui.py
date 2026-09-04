from yt_downloader.core.models import AppSettings
from yt_downloader.ui.main_window import MainWindow
from yt_downloader.ui.pages.settings_page import SettingsPage


def test_settings_page_has_stable_update_controls_and_persists_checkbox(qtbot, tmp_path):
    settings = AppSettings(download_directory=str(tmp_path), auto_check_updates=False)
    page = SettingsPage(settings, ytdlp_version='x', ffmpeg_description='x')
    qtbot.addWidget(page)
    assert page.update_channel_label.text() == '稳定通道'
    assert page.update_check_button.text() == '检查更新'
    assert not page.auto_check_updates.isChecked()
    page.auto_check_updates.setChecked(True)
    assert page.current_settings().auto_check_updates is True


def test_main_window_uses_non_modal_update_banner(qtbot, tmp_path):
    window = MainWindow(AppSettings(download_directory=str(tmp_path)), ytdlp_version='x', ffmpeg_description='x')
    qtbot.addWidget(window)
    window.show()
    window.show_update_available('0.4.1')
    assert window.update_banner.isVisible()
    assert '0.4.1' in window.update_banner_label.text()
    window.update_banner_close.click()
    assert not window.update_banner.isVisible()

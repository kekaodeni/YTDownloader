from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from semver import Version

from yt_downloader.updates.models import UpdateCapability, UpdateManifest, UpdatePackage, UpdateProgress, UpdateState
from yt_downloader.ui.quick_dialogs import UpdateSession as UpdateDialog


def _manifest():
    return UpdateManifest(
        Version.parse('0.4.1'), '2026-09-04T10:00:00Z', Version.parse('0.4.0'), 1,
        'key', '中文说明', 'English notes', 'https://example.invalid/release',
        UpdatePackage('x.zip', 'https://example.invalid/x.zip', 100, 200, '0' * 64),
    )


def test_check_only_dialog_never_offers_download_or_install(quick_window):
    dialog = UpdateDialog(_manifest(), UpdateCapability.CHECK_ONLY, quick_window)
    assert dialog.state['canRelease']
    assert not dialog.state['canDownload']
    assert not dialog.state['canInstall']


def test_update_dialog_download_progress_cancel_and_ready_install(quick_window, qtbot):
    dialog = UpdateDialog(_manifest(), UpdateCapability.AUTO_INSTALL, quick_window)
    dialog.show()
    with qtbot.waitSignal(dialog.download_requested, timeout=500):
        dialog.action('download')
    dialog.set_state(UpdateState.DOWNLOADING)
    dialog.set_progress(UpdateProgress(25, 100))
    assert dialog.state['progress'] == .25
    with qtbot.waitSignal(dialog.cancel_requested, timeout=500):
        dialog.action('cancel')
    dialog.set_state(UpdateState.READY_TO_INSTALL)
    assert dialog.state['canInstall']


def test_validation_build_stops_at_verified_package(quick_window):
    dialog = UpdateDialog(_manifest(), UpdateCapability.DOWNLOAD_AND_VERIFY, quick_window)
    dialog.set_state(UpdateState.READY_TO_INSTALL)
    assert '不支持自动安装' in dialog.state['message']
    assert not dialog.state['canInstall']

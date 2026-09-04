from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from semver import Version

from yt_downloader.updates.models import UpdateCapability, UpdateManifest, UpdatePackage, UpdateProgress, UpdateState
from yt_downloader.ui.widgets.update_dialog import UpdateDialog


def _manifest():
    return UpdateManifest(
        Version.parse('0.4.1'), '2026-09-04T10:00:00Z', Version.parse('0.4.0'), 1,
        'key', '中文说明', 'English notes', 'https://example.invalid/release',
        UpdatePackage('x.zip', 'https://example.invalid/x.zip', 100, 200, '0' * 64),
    )


def _button(dialog, text):
    return next(button for button in dialog.findChildren(QPushButton) if button.text() == text)


def test_check_only_dialog_never_offers_download_or_install(qtbot):
    dialog = UpdateDialog(_manifest(), UpdateCapability.CHECK_ONLY)
    qtbot.addWidget(dialog)
    assert _button(dialog, '打开发布页面').isVisibleTo(dialog)
    assert not any(b.text() == '下载并验证' for b in dialog.findChildren(QPushButton) if b.isVisibleTo(dialog))
    assert not any(b.text() == '退出并更新' for b in dialog.findChildren(QPushButton) if b.isVisibleTo(dialog))


def test_update_dialog_download_progress_cancel_and_ready_install(qtbot):
    dialog = UpdateDialog(_manifest(), UpdateCapability.AUTO_INSTALL)
    qtbot.addWidget(dialog); dialog.show()
    with qtbot.waitSignal(dialog.download_requested, timeout=500):
        _button(dialog, '下载并验证').click()
    dialog.set_state(UpdateState.DOWNLOADING)
    dialog.set_progress(UpdateProgress(25, 100))
    assert dialog.progress_bar.value() == 25
    with qtbot.waitSignal(dialog.cancel_requested, timeout=500):
        _button(dialog, '取消下载').click()
    dialog.set_state(UpdateState.READY_TO_INSTALL)
    assert _button(dialog, '退出并更新').isVisible()


def test_validation_build_stops_at_verified_package(qtbot):
    dialog = UpdateDialog(_manifest(), UpdateCapability.DOWNLOAD_AND_VERIFY)
    qtbot.addWidget(dialog); dialog.show()
    dialog.set_state(UpdateState.READY_TO_INSTALL)
    assert '不支持自动安装' in dialog.status_label.text()
    assert not any(b.text() == '退出并更新' and b.isVisible() for b in dialog.findChildren(QPushButton))

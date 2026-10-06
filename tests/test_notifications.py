from types import SimpleNamespace
from dataclasses import replace
import pytest
from test_download_service import _request


def _coordinator(tmp_path, **options):
    from yt_downloader.services.notification_service import NotificationCoordinator
    from yt_downloader.ui.localization import Translator
    system, internal = [], []
    sink = SimpleNamespace(send=lambda title, body: system.append((title, body)))
    notification = NotificationCoordinator(Translator('en-US'), sink,
        is_foreground=lambda: options.get('foreground', False),
        enabled=lambda: options.get('enabled', True), inline=lambda title, body: internal.append((title, body)))
    return notification, system, internal


def test_single_download_success_notification(tmp_path):
    notification, system, _ = _coordinator(tmp_path)
    request = _request(tmp_path)
    notification.finished(request, 'completed')
    assert system == [('Download complete', request.video.title)]


def test_single_download_failure_notification(tmp_path):
    notification, system, _ = _coordinator(tmp_path)
    request = _request(tmp_path)
    notification.finished(request, 'failed')
    assert system == [('Download failed', request.video.title)]


def test_notifications_disabled(tmp_path):
    notification, system, internal = _coordinator(tmp_path, enabled=False)
    notification.finished(_request(tmp_path), 'completed')
    assert not system and not internal


def test_playlist_notification_aggregation(tmp_path):
    notification, system, _ = _coordinator(tmp_path)
    requests = [replace(_request(tmp_path), task_id=str(i), batch_id='batch') for i in range(28)]
    notification.register_batch(requests)
    for request in requests[:-1]: notification.finished(request, 'completed')
    assert system == []
    notification.finished(requests[-1], 'failed')
    assert system == [('Batch download complete', '27 completed, 1 failed')]
    notification.finished(requests[-1], 'failed')
    assert len(system) == 1


@pytest.mark.parametrize('outcome', ['completed', 'failed'])
def test_foreground_notification_policy(tmp_path, outcome):
    notification, system, internal = _coordinator(tmp_path, foreground=True)
    notification.finished(_request(tmp_path), outcome)
    assert not system and not internal


def test_foreground_batch_is_consumed_without_fallback(tmp_path):
    notification, system, internal = _coordinator(tmp_path, foreground=True)
    requests = [replace(_request(tmp_path), task_id=str(i), batch_id='front') for i in range(3)]
    notification.register_batch(requests)
    for request in requests: notification.finished(request, 'completed')
    notification.is_foreground = lambda: False
    for request in requests: notification.finished(request, 'completed')
    assert not system and not internal


def test_foreground_event_is_consumed_before_alt_tab(tmp_path):
    notification, system, internal = _coordinator(tmp_path, foreground=True)
    request = _request(tmp_path)
    notification.finished(request, 'completed')
    notification.is_foreground = lambda: False
    notification.finished(request, 'completed')
    assert not system and not internal


def test_disabled_event_is_not_replayed_after_enabling(tmp_path):
    notification, system, internal = _coordinator(tmp_path, enabled=False)
    request = _request(tmp_path)
    notification.finished(request, 'failed')
    notification.enabled = lambda: True
    notification.finished(request, 'failed')
    assert not system and not internal


def test_foreground_requires_visible_active_non_minimized_window():
    from PySide6.QtCore import Qt
    from yt_downloader.services.notification_service import is_app_foreground
    for visible, active, minimized, application_active in (
        (True, True, False, True), (False, True, False, True),
        (True, False, False, True), (True, True, True, True),
        (True, True, False, False),
    ):
        window = SimpleNamespace(isVisible=lambda: visible, isActive=lambda: active,
                                 windowState=lambda: Qt.WindowMinimized if minimized else Qt.WindowNoState)
        application = SimpleNamespace(applicationState=lambda: Qt.ApplicationActive if application_active else Qt.ApplicationInactive)
        assert is_app_foreground(window, application) == (visible and active and not minimized and application_active)


def test_explicit_task_retry_has_a_new_notification_attempt(tmp_path):
    notification, system, _ = _coordinator(tmp_path)
    request = _request(tmp_path)
    notification.finished(request, 'failed')
    notification.queued(request)
    notification.finished(request, 'completed')
    notification.finished(request, 'completed')
    assert [title for title, body in system] == ['Download failed', 'Download complete']


def test_batch_cancellations_are_reported_honestly(tmp_path):
    notification, system, _ = _coordinator(tmp_path)
    requests = [replace(_request(tmp_path), task_id=str(i), batch_id='cancelled-batch') for i in range(3)]
    notification.register_batch(requests)
    for request, status in zip(requests, ['completed', 'failed', 'cancelled']): notification.finished(request, status)
    assert system == [('Batch download complete', '1 completed, 1 failed, 1 cancelled')]


def test_notification_xml_escapes_untrusted_video_titles():
    from xml.etree.ElementTree import fromstring
    from yt_downloader.infrastructure.windows_notifications import toast_xml
    raw = 'A < B & C $(nothing) 日本語'
    tree = fromstring(toast_xml('Title', raw))
    assert [element.text for element in tree.findall('./visual/binding/text')] == ['Title', raw]
    assert tree.find('./audio').get('silent') == 'true'


def test_windows_bridge_uses_hidden_process_without_window_style(monkeypatch):
    from yt_downloader.infrastructure.windows_notifications import send_windows_toast
    import winreg
    import subprocess
    monkeypatch.setattr('yt_downloader.infrastructure.windows_notifications.register_shortcut', lambda _icon: {})
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(winreg, 'CreateKey', lambda *args: Key())
    monkeypatch.setattr(winreg, 'SetValueEx', lambda *args: None)
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda args, **options:
        (calls.append((args, options)), SimpleNamespace(returncode=0, stdout='{"in_history":true}'))[1])
    assert send_windows_toast('Title', 'Body')['in_history']
    command, options = calls[0]
    assert '-WindowStyle' not in command
    assert options['creationflags'] == subprocess.CREATE_NO_WINDOW
    assert options['stdin'] == subprocess.DEVNULL


def test_windows_bridge_timeout_does_not_log_encoded_payload(monkeypatch):
    from yt_downloader.infrastructure.windows_notifications import send_windows_toast
    import winreg
    import subprocess
    import pytest
    monkeypatch.setattr('yt_downloader.infrastructure.windows_notifications.register_shortcut', lambda _icon: {})
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(winreg, 'CreateKey', lambda *args: Key())
    monkeypatch.setattr(winreg, 'SetValueEx', lambda *args: None)
    def timeout(command, **options): raise subprocess.TimeoutExpired(command, 15)
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(RuntimeError, match='timed out') as error:
        send_windows_toast('Title', 'private video title')
    assert 'EncodedCommand' not in str(error.value)


def test_windows_identity_uses_product_name_and_official_shortcut_api():
    from yt_downloader.infrastructure.windows_app_identity import AUMID, DISPLAY_NAME, PROPVARIANT
    import ctypes
    assert AUMID == 'YTDownloader'
    assert DISPLAY_NAME == 'YT Downloader'
    assert ctypes.sizeof(PROPVARIANT) == (24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16)

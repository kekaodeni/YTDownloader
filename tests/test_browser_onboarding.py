from pathlib import Path
import sys

import pytest
from PySide6.QtCore import QPointF, QProcess, QTimer
from PySide6.QtGui import QDesktopServices

from conftest import click_item, find_item, run_frames
from yt_downloader.browser_companion.registration import ConnectionManager, default_bridge_path


def reveal(window, app, item):
    scroll = find_item(window, 'browserCompanionScroll')
    y = item.mapToItem(scroll.property('contentItem'), QPointF(0, 0)).y()
    scroll.setProperty('contentY', max(0, min(y - scroll.height() / 2,
                                            scroll.property('contentHeight') - scroll.height())))
    run_frames(app, 80)
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    assert item.isVisible() and item.isEnabled()
    assert 0 <= point.x() < window.root.width() and 0 <= point.y() < window.root.height()
    return scroll


class TestRegistry:
    __test__ = False
    def __init__(self): self.values = {}
    def read(self, browser): return self.values.get(browser, '')
    def write(self, browser, path): self.values[browser] = str(path)
    def remove(self, browser, expected):
        if self.read(browser) != str(expected): return False
        self.values.pop(browser, None)
        return True


def isolated_manager(window, tmp_path):
    bridge = tmp_path / 'package/YTDownloaderBridge.exe'
    bridge.parent.mkdir(parents=True)
    bridge.write_bytes(b'controlled test host')
    manager = ConnectionManager(tmp_path / 'data', registry=TestRegistry(), bridge_path=bridge)
    window.browser_companion.manager = manager
    window.browser_companion.refresh()
    return manager


def open_browser(window, app, browser):
    window.root.resize(1180, 850)
    window._select_page(2)
    window.toolbox_page.selectCategory(2)
    run_frames(app, 220)
    click_item(window, find_item(window, 'browser-select-' + browser))
    run_frames(app, 80)


def confirm_remove_by_mouse(window, app):
    run_frames(app, 220)
    dialog = find_item(window, 'dialog-confirm')
    pending = [dialog.property('footer'), dialog.property('contentItem')]
    while pending:
        item = pending.pop()
        if item is None: continue
        if hasattr(item, 'clicked') and item.property('text') == window.i18n.text('browser.remove'):
            click_item(window, item)
            return
        pending.extend(item.childItems())
    raise AssertionError('visible confirmation action not found')


@pytest.mark.parametrize('browser', ['chrome', 'edge', 'firefox'])
def test_missing_bridge_real_click_has_local_actionable_feedback(quick_window, qapp, monkeypatch, tmp_path, browser):
    monkeypatch.setenv('YT_DOWNLOADER_BRIDGE_EXE', str(tmp_path / 'missing/YTDownloaderBridge.exe'))
    w = quick_window
    w.browser_companion.manager.bridge_path = tmp_path / 'missing/YTDownloaderBridge.exe'
    w._select_page(2)
    w.toolbox_page.selectCategory(2)
    run_frames(qapp, 250)
    click_item(w, find_item(w, 'browser-select-' + browser))
    run_frames(qapp, 100)
    button = find_item(w, 'browser-install-' + browser)
    clicked = []
    busy = []
    button.clicked.connect(lambda: clicked.append(True))
    w.browser_companion.operationStarted.connect(lambda *_: busy.append(w.browser_companion.state['rows'][['chrome', 'edge', 'firefox'].index(browser)]['busy']))
    click_item(w, button)
    assert busy == [True]
    run_frames(qapp, 160)
    assert clicked == [True]
    row = w.browser_companion.state['rows'][['chrome', 'edge', 'firefox'].index(browser)]
    assert row['noticeKey'] == 'browser.bridge_missing'
    notice = find_item(w, 'browser-notice-install-' + browser)
    assert notice.isVisible()
    point = notice.mapToScene(QPointF(0, 0))
    assert 0 <= point.y() < w.root.height() - notice.height()
    assert find_item(w, 'browser-copy-build-' + browser).isVisible()
    assert not row['busy']
    assert not w.qml_warnings


@pytest.mark.parametrize('browser', ['chrome', 'edge', 'firefox'])
@pytest.mark.parametrize('action', ['install', 'test', 'repair', 'remove', 'folder'])
def test_fifteen_real_button_clicks_execute_and_show_local_result(quick_window, qapp, monkeypatch, tmp_path, browser, action):
    """Real Qt mouse events + real manager files; registry/probe/OS opener controlled here.

    Actual HKCU, frozen Bridge, pipe and OS-folder checks are a separate live harness.
    """
    w = quick_window
    manager = isolated_manager(w, tmp_path)
    p = w.browser_companion
    if action != 'install': manager.install(browser)
    if action == 'repair':
        moved = tmp_path / 'moved/YTDownloaderBridge.exe'
        moved.parent.mkdir(); moved.write_bytes(b'moved test host')
        manager.bridge_path = moved
    calls, opened, starts, busy = [], [], [], []
    for method in ('install', 'remove'):
        original = getattr(manager, method)
        def tracked(*args, name=method, original=original, **kwargs):
            calls.append((name, args[0])); return original(*args, **kwargs)
        monkeypatch.setattr(manager, method, tracked)
    def probe(b, a):
        calls.append(('probe', b))
        def finish():
            p.tested[b] = True
            p._complete(b, a, 'test_in_browser' if a == 'test' else 'connection_configured')
        QTimer.singleShot(100, finish)
    monkeypatch.setattr(p, '_probe', probe)
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True)
    p.operationStarted.connect(lambda b, a: (starts.append((b, a)), busy.append(p.state['rows'][['chrome', 'edge', 'firefox'].index(b)]['busy'])))
    p.refresh(); open_browser(w, qapp, browser)
    if action in {'repair', 'remove'}:
        toggle = find_item(w, 'browser-advanced-' + browser)
        reveal(w, qapp, toggle); click_item(w, toggle); run_frames(qapp, 100)
    button = find_item(w, f'browser-{action}-{browser}')
    clicked = []
    button.clicked.connect(lambda: clicked.append(True))
    scroll = reveal(w, qapp, button)
    before_y = scroll.property('contentY')
    click_item(w, button)
    if action == 'remove':
        assert manager.status(browser) == 'configured'
        assert ('remove', browser) not in calls
        confirm_remove_by_mouse(w, qapp)
    run_frames(qapp, 220)
    row = p.state['rows'][['chrome', 'edge', 'firefox'].index(browser)]
    assert starts == [(browser, action)] and clicked == [True] and busy == [True]
    assert not row['busy'] and not row['noticeError']
    area = 'repair' if action == 'remove' else action
    notice = find_item(w, f'browser-notice-{area}-{browser}')
    assert notice.isVisible() and notice.property('text') == w.i18n.text(row['noticeKey'])
    point = notice.mapToScene(QPointF(0, 0))
    assert 0 <= point.y() < w.root.height() - notice.height()
    assert abs(scroll.property('contentY') - before_y) < 1
    if action in {'install', 'repair'}:
        assert ('install', browser) in calls and ('probe', browser) in calls
        assert manager.status(browser) == 'configured' and row['connectionState'] == 'HOST_READY'
    elif action == 'test':
        assert ('probe', browser) in calls and not row['connected']
    elif action == 'remove':
        assert ('remove', browser) in calls and manager.status(browser) == 'not_configured'
        assert manager.extension_folder(browser).is_dir()
    else:
        assert [Path(path) for path in opened] == [manager.extension_folder(browser)]


@pytest.mark.parametrize('failure', ['folder_missing', 'registration_conflict', 'repair_needed', 'open_failed', 'timeout', 'ipc_unavailable'])
def test_real_click_failure_is_visible_and_actionable(quick_window, qapp, monkeypatch, tmp_path, failure):
    w = quick_window
    manager = isolated_manager(w, tmp_path)
    p = w.browser_companion
    browser, action = 'chrome', 'test'
    if failure == 'folder_missing': action = 'folder'
    elif failure == 'registration_conflict':
        manager.registry.values['chrome'] = 'another-installation.json'
        action = 'install'
    else:
        manager.install(browser)
        if failure == 'repair_needed': manager.registry.values['chrome'] = ''
        if failure == 'open_failed':
            action = 'folder'
            monkeypatch.setattr(QDesktopServices, 'openUrl', lambda *_: False)
        if failure in {'timeout', 'ipc_unavailable'}:
            script = tmp_path / 'host.py'
            script.write_text('import time; time.sleep(10)' if failure == 'timeout' else
                "import sys,struct,json\nn=struct.unpack('<I',sys.stdin.buffer.read(4))[0];m=json.loads(sys.stdin.buffer.read(n));r=dict(protocol=1,request_id=m['request_id'],status='accepted',bridge_ready=True,app_running=False);b=json.dumps(r).encode();sys.stdout.buffer.write(struct.pack('<I',len(b))+b);sys.stdout.buffer.flush()", 'utf-8')
            class Process(QProcess):
                def start(self, *_): super().start(sys.executable, [str(script)])
            import yt_downloader.ui.quick_browser_companion as module
            monkeypatch.setattr(module, 'QProcess', Process)
            p.probe_timeout_ms = 100 if failure == 'timeout' else 3000
    p.refresh(); open_browser(w, qapp, browser)
    button = find_item(w, f'browser-{action}-{browser}')
    reveal(w, qapp, button); click_item(w, button)
    for _ in range(30):
        run_frames(qapp, 100)
        if not p.state['rows'][0]['busy']: break
    row = p.state['rows'][0]
    expected = 'test_timeout' if failure == 'timeout' else failure
    assert row['noticeKey'] == 'browser.' + expected and row['noticeError'] and not row['busy']
    notice = find_item(w, f'browser-notice-{action}-{browser}')
    assert notice.isVisible() and notice.property('text') == w.i18n.text(row['noticeKey'])
    assert not row['hostReady']


def test_local_ready_is_not_browser_installation_and_feedback_is_per_browser(quick_window, qapp, tmp_path, monkeypatch):
    w = quick_window
    manager = isolated_manager(w, tmp_path)
    p = w.browser_companion
    manager.install('chrome'); p.tested['chrome'] = True; p.refresh()
    assert p.state['rows'][0]['connectionState'] == 'HOST_READY'
    assert not p.state['rows'][0]['connected']
    p._notice('chrome', 'folder_missing', 'folder', error=True)
    p._notice('edge', 'registration_conflict', 'install', error=True)
    assert p.state['rows'][0]['noticeKey'] == 'browser.folder_missing'
    assert p.state['rows'][1]['noticeKey'] == 'browser.registration_conflict'
    p.mark_seen('chrome')
    assert p.state['rows'][0]['connectionState'] == 'CONNECTED'
    assert not p.state['rows'][1]['connected']


def test_bridge_discovery_is_explicit_source_or_beside_frozen_app(monkeypatch, tmp_path):
    from yt_downloader.infrastructure.runtime import resource_path
    monkeypatch.delenv('YT_DOWNLOADER_BRIDGE_EXE', raising=False)
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    assert default_bridge_path() == resource_path('build/browser-bridge/YTDownloaderBridge.exe')
    monkeypatch.setenv('YT_DOWNLOADER_BRIDGE_EXE', str(tmp_path / 'explicit/YTDownloaderBridge.exe'))
    assert default_bridge_path() == tmp_path / 'explicit/YTDownloaderBridge.exe'
    monkeypatch.setattr(sys, 'frozen', True)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'portable/YTDownloader.exe'))
    assert default_bridge_path() == tmp_path / 'portable/YTDownloaderBridge.exe'


@pytest.mark.parametrize('browser', ['chrome', 'edge', 'firefox'])
def test_running_operation_ignores_repeated_mouse_clicks(quick_window, qapp, monkeypatch, tmp_path, browser):
    w = quick_window
    isolated_manager(w, tmp_path)
    p = w.browser_companion
    starts, probes = [], []
    p.operationStarted.connect(lambda b, a: starts.append((b, a)))
    monkeypatch.setattr(p, '_probe', lambda b, a: probes.append((b, a)))
    open_browser(w, qapp, browser)
    button = find_item(w, 'browser-install-' + browser)
    click_item(w, button)
    run_frames(qapp, 80)
    assert not button.isEnabled()
    for _ in range(5):
        click_item(w, button)
    assert starts == [(browser, 'install')] and probes == starts
    assert p.state['rows'][['chrome', 'edge', 'firefox'].index(browser)]['busy']
    p._complete(browser, 'install', 'connection_configured')
    run_frames(qapp, 80)
    assert button.isEnabled()


def test_remove_cancel_by_mouse_keeps_registration(quick_window, qapp, tmp_path):
    w = quick_window
    manager = isolated_manager(w, tmp_path)
    manager.install('chrome')
    w.browser_companion.refresh()
    open_browser(w, qapp, 'chrome')
    toggle = find_item(w, 'browser-advanced-chrome')
    reveal(w, qapp, toggle); click_item(w, toggle); run_frames(qapp, 100)
    button = find_item(w, 'browser-remove-chrome')
    reveal(w, qapp, button); click_item(w, button); run_frames(qapp, 220)
    dialog = find_item(w, 'dialog-confirm')
    pending = [dialog.property('footer'), dialog.property('contentItem')]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        if hasattr(item, 'clicked') and item.property('text') == w.i18n.text('common.cancel'):
            click_item(w, item)
            break
        pending.extend(item.childItems())
    else:
        raise AssertionError('visible cancellation action not found')
    run_frames(qapp, 100)
    assert manager.status('chrome') == 'configured'
    assert w.browser_companion.state['rows'][0]['noticeKey'] == 'browser.remove_cancelled'
    assert not w.browser_companion.state['rows'][0]['busy']

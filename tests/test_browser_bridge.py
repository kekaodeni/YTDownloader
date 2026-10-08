import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from yt_downloader.browser_companion.bridge import NativeBridge, authorize_caller, launch_app
from yt_downloader.browser_companion.protocol import ProtocolError, response
from yt_downloader.browser_companion.registration import ConnectionManager

ROOT = Path(__file__).resolve().parents[1]

class Registry:
    def __init__(self): self.values = {}
    def read(self, browser): return self.values.get(browser, '')
    def write(self, browser, path): self.values[browser] = str(path)
    def remove(self, browser, expected):
        if self.read(browser) != str(expected): return False
        self.values.pop(browser, None)
        return True

@pytest.fixture
def manager(tmp_path):
    bridge = tmp_path / 'portable/YTDownloaderBridge.exe'
    bridge.parent.mkdir()
    bridge.write_bytes(b'test executable')
    return ConnectionManager(tmp_path / 'data', registry=Registry(), resources=ROOT / 'browser-extension', bridge_path=bridge)

@pytest.mark.parametrize('browser', ['chrome','edge','firefox'])
def test_register_exact_identity_and_remove_only_owned(manager, browser):
    user_file = manager.root.parent / 'history.json'
    user_file.parent.mkdir(exist_ok=True)
    user_file.write_text('keep')
    folder = manager.install(browser)
    manifest = json.loads(manager.manifest_path(browser).read_text())
    assert manifest['type'] == 'stdio'
    assert '*' not in json.dumps(manifest)
    assert 'allowed_extensions' in manifest if browser == 'firefox' else 'allowed_origins' in manifest
    assert (folder / 'popup.html').is_file()
    assert manager.status(browser) == 'configured'
    assert manager.remove(browser)
    assert not manager.registry.read(browser)
    assert manager.status(browser) == 'not_configured'
    assert user_file.read_text() == 'keep'
    assert folder.is_dir()

def test_registration_conflict_and_rollback(manager, monkeypatch):
    manager.registry.values['chrome'] = 'other-owner.json'
    with pytest.raises(ProtocolError): manager.install('chrome')
    assert manager.registry.read('chrome') == 'other-owner.json'
    manager.registry.values.clear()
    def fail(*args): raise OSError()
    monkeypatch.setattr(manager.registry, 'write', fail)
    with pytest.raises(OSError): manager.install('chrome')
    assert not manager.config_path.exists()
    assert not manager.manifest_path('chrome').exists()

def test_portable_move_repair(manager):
    manager.install('edge')
    moved = manager.bridge_path.parent / 'moved/YTDownloaderBridge.exe'
    moved.parent.mkdir()
    moved.write_bytes(manager.bridge_path.read_bytes())
    manager.bridge_path = moved
    assert manager.status('edge') == 'repair_needed'
    manager.install('edge')
    assert manager.status('edge') == 'configured'
    assert json.loads(manager.manifest_path('edge').read_text())['path'] == str(moved.resolve())

def test_origins_and_firefox_argv_are_pinned(manager):
    for browser in ['chrome','edge','firefox']: manager.install(browser)
    config = manager.load()
    for browser in ['chrome','edge']:
        origin = 'chrome-extension://' + manager.identity(browser) + '/'
        assert authorize_caller([origin,'--parent-window=0'],config,manager.root) == browser
    assert authorize_caller([str(manager.manifest_path('firefox')),manager.identity('firefox')],config,manager.root) == 'firefox'
    for argv in [['chrome-extension://' + 'a'*32 + '/'],['https://example.org/'],
                 [str(manager.manifest_path('edge')),manager.identity('firefox')],
                 ['chrome-extension://' + manager.identity('chrome') + '/','--execute=calc']]:
        with pytest.raises(ProtocolError): authorize_caller(argv,config,manager.root)

def test_send_reuses_ipc_and_does_not_launch_or_download():
    launch = Mock()
    client = Mock(side_effect=lambda m: response(m['request_id'],'delivered'))
    bridge = NativeBridge({},'chrome',client=client,launcher=launch)
    message = dict(protocol=1,action='send_url',request_id='one',url='https://example.org/$(calc);powershell')
    assert bridge.handle(message)['status'] == 'delivered'
    assert bridge.handle(message)['status'] == 'delivered'
    assert client.call_count == 1
    assert client.call_args.args[0] == dict(message,browser='chrome')
    launch.assert_not_called()
    assert bridge.handle(dict(message,url='https://example.org/other'))['status'] == 'invalid_message'

def test_startup_race_waits_and_delivers():
    client = Mock(side_effect=[OSError(),OSError(),response('one','delivered')])
    launch = Mock()
    bridge = NativeBridge({},'firefox',client=client,launcher=launch,timeout=1)
    assert bridge.handle(dict(protocol=1,action='send_url',request_id='one',url='https://example.org/'))['status'] == 'delivered'
    launch.assert_called_once_with({})

def test_ping_never_starts_app_and_errors_are_not_leaked():
    launch = Mock()
    bridge = NativeBridge({},'edge',client=Mock(side_effect=OSError('SESSDATA=secret')),launcher=launch)
    result = bridge.handle(dict(protocol=1,action='ping',request_id='p'))
    assert result['bridge_ready'] and not result['app_running']
    assert 'secret' not in json.dumps(result)
    launch.assert_not_called()

def test_launch_argv_contains_only_fixed_app(manager, monkeypatch):
    exe = manager.bridge_path.parent / 'YTDownloader.exe'
    exe.write_bytes(b'test')
    spawn = Mock()
    monkeypatch.setattr('yt_downloader.browser_companion.bridge.subprocess.Popen', spawn)
    launch_app(dict(launch=dict(mode='frozen',path=str(exe))))
    assert spawn.call_args.args[0] == [str(exe)]
    assert not spawn.call_args.kwargs.get('shell',False)
    with pytest.raises(ProtocolError): launch_app(dict(launch=dict(mode='frozen',path='powershell.exe')))

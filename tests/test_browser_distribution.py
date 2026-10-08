import json
import sys
from pathlib import Path

import pytest

from test_browser_bridge import Registry
from yt_downloader.browser_companion.registration import ConnectionManager
from yt_downloader.browser_companion.protocol import ProtocolError

ASSETS = Path(__file__).resolve().parents[1] / 'browser-extension'


def manager_for(tmp_path):
    bridge = tmp_path / 'portable/YTDownloaderBridge.exe'
    bridge.parent.mkdir(exist_ok=True)
    bridge.write_bytes(b'controlled host')
    return ConnectionManager(tmp_path / 'data', registry=Registry(), resources=ASSETS, bridge_path=bridge)


@pytest.mark.parametrize('browser,folder_name', [('chrome','Chrome'),('edge','Edge'),('firefox','Firefox')])
def test_source_exports_beside_bridge_without_appdata_copy(tmp_path, browser, folder_name):
    manager = manager_for(tmp_path)
    folder = manager.install(browser)
    assert folder == manager.bridge_path.parent / 'BrowserExtensions' / folder_name
    assert (folder / 'manifest.json').is_file() and (folder / 'popup.html').is_file()
    assert not (manager.root / 'extensions').exists()
    assert manager.load()['browsers'][browser]['extension_path'] == str(folder.resolve())


def test_distribution_uses_one_manifest_source_and_preserves_existing_files(tmp_path):
    from yt_downloader.browser_companion.distribution import bundle_extensions
    destination = tmp_path / 'BrowserExtensions'
    bundle_extensions(ASSETS, destination)
    for browser,folder in [('chrome','Chrome'),('edge','Edge'),('firefox','Firefox')]:
        manifest = json.loads((destination/folder/'manifest.json').read_text('utf-8'))
        assert manifest == json.loads((ASSETS/'manifests'/(browser+'.json')).read_text('utf-8'))
        assert len(list((destination/folder/'_locales').glob('*/messages.json'))) == 10
    foreign = destination/'Chrome/popup.html'
    foreign.write_text('user content','utf-8')
    with pytest.raises(FileExistsError):
        bundle_extensions(ASSETS,destination)
    assert foreign.read_text('utf-8') == 'user content'


def test_frozen_uses_shipped_read_only_directory_without_writing_it(tmp_path,monkeypatch):
    from yt_downloader.browser_companion.distribution import bundle_extensions
    manager = manager_for(tmp_path)
    bundle_extensions(ASSETS, manager.bridge_path.parent/'BrowserExtensions')
    before = {str(p):p.read_bytes() for p in (manager.bridge_path.parent/'BrowserExtensions').rglob('*') if p.is_file()}
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(manager.bridge_path.parent/'YTDownloader.exe'))
    def forbidden(*_args,**_kwargs):raise AssertionError('frozen installation must not copy assets')
    monkeypatch.setattr('yt_downloader.browser_companion.distribution.bundle_extensions',forbidden)
    manager.install('chrome')
    assert before == {str(p):p.read_bytes() for p in (manager.bridge_path.parent/'BrowserExtensions').rglob('*') if p.is_file()}
    assert not (manager.root/'extensions').exists()


def test_missing_frozen_extensions_keep_previous_configuration(tmp_path,monkeypatch):
    manager = manager_for(tmp_path)
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(manager.bridge_path.parent/'YTDownloader.exe'))
    with pytest.raises(ProtocolError,match='extension_missing'):
        manager.install('chrome')
    assert not manager.config_path.exists() and not manager.registry.read('chrome')


def test_legacy_appdata_migration_keeps_files_identity_and_requires_reload(tmp_path):
    manager = manager_for(tmp_path)
    manager.install('chrome','a'*32)
    old = manager.root/'extensions/chrome';old.mkdir(parents=True)
    (old/'user.txt').write_text('keep','utf-8')
    config = manager.load()
    config['browsers']['chrome'].pop('extension_path')
    manager._write(manager.config_path,config)
    location = manager.extension_location('chrome')
    assert location['reload_required'] and location['previous_path'] == str(old.resolve())
    manager.install('chrome')
    assert (old/'user.txt').read_text('utf-8') == 'keep'
    current = manager.load()['browsers']['chrome']
    assert current['extension_id'] == 'a'*32 and current['extension_reload_required']
    manager.confirm_extension_reload('chrome')
    assert not manager.extension_location('chrome')['reload_required']


def test_portable_move_requires_browser_reload_even_after_host_repair(tmp_path):
    manager = manager_for(tmp_path)
    manager.install('edge')
    original = manager.extension_folder('edge')
    moved = tmp_path/'moved/YTDownloaderBridge.exe';moved.parent.mkdir();moved.write_bytes(b'host')
    manager.bridge_path = moved
    assert manager.extension_location('edge')['reload_required']
    manager.install('edge')
    assert manager.status('edge') == 'configured'
    assert manager.extension_location('edge')['reload_required']
    assert manager.extension_location('edge')['previous_path'] == str(original.resolve())

"""User-owned Windows Native Host associations, never HKLM or browser cookies."""
import json
import os
from pathlib import Path
import re
import sys
from .protocol import HOST_NAME, PROTOCOL, ProtocolError
from .distribution import BROWSER_FOLDERS

REGISTRY_ROOTS = {'chrome': r'Software\Google\Chrome\NativeMessagingHosts',
                  'edge': r'Software\Microsoft\Edge\NativeMessagingHosts',
                  'firefox': r'Software\Mozilla\NativeMessagingHosts'}

class WindowsRegistry:
    def read(self, browser):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_ROOTS[browser] + '\\' + HOST_NAME,
                               0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                return winreg.QueryValueEx(key, '')[0]
        except FileNotFoundError: return ''

    def write(self, browser, path):
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_ROOTS[browser] + '\\' + HOST_NAME,
                               0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(path))
            winreg.SetValueEx(key, 'YTDownloaderOwner', 0, winreg.REG_SZ, HOST_NAME)

    def remove(self, browser, expected):
        import winreg
        path = REGISTRY_ROOTS[browser] + '\\' + HOST_NAME
        if self.read(browser) != str(expected): return False
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            try:
                if winreg.QueryValueEx(key, 'YTDownloaderOwner')[0] != HOST_NAME: return False
            except FileNotFoundError: return False
            count = winreg.QueryInfoKey(key)[1]
            if any(winreg.EnumValue(key, index)[0] not in {'', 'YTDownloaderOwner'} for index in range(count)): return False
        winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, path, winreg.KEY_WOW64_64KEY)
        return True

def assets_root():
    from yt_downloader.infrastructure.runtime import resource_path
    return resource_path('browser-extension')

def default_bridge_path():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'YTDownloaderBridge.exe'
    from yt_downloader.infrastructure.runtime import resource_path
    return Path(os.environ.get('YT_DOWNLOADER_BRIDGE_EXE') or
                resource_path('build/browser-bridge/YTDownloaderBridge.exe'))

def valid_extension_id(browser, value):
    if not isinstance(value, str): return False
    return bool(re.fullmatch(r'[a-p]{32}', value) if browser != 'firefox' else
                re.fullmatch(r'[A-Za-z0-9._-]+@[A-Za-z0-9.-]+|\{[0-9a-fA-F-]{36}\}', value))

class ConnectionManager:
    def __init__(self, data_directory, *, registry=None, resources=None, bridge_path=None):
        self.root = Path(data_directory) / 'browser-companion'
        self.resources = Path(resources) if resources else assets_root()
        self.registry = registry or WindowsRegistry()
        self.bridge_path = Path(bridge_path) if bridge_path else default_bridge_path()
        self.config_path = self.root / 'connection.json'

    def identity(self, browser):
        return json.loads((self.resources / 'identity.json').read_text('utf-8'))[browser]['id']

    def load(self):
        if not self.config_path.is_file(): return {}
        if self.config_path.stat().st_size > 65536: raise ProtocolError('host_unavailable')
        config = json.loads(self.config_path.read_text('utf-8'))
        if config.get('owner') != HOST_NAME or config.get('protocol') != PROTOCOL: raise ProtocolError('host_unavailable')
        return config

    def manifest_path(self, browser): return self.root / (browser + '.json')

    def extension_folder(self, browser):
        return self.bridge_path.parent / 'BrowserExtensions' / BROWSER_FOLDERS[browser]

    def extension_location(self, browser):
        item = self.load().get('browsers', {}).get(browser, {})
        legacy = self.root / 'extensions' / browser
        previous = item.get('extension_path') or (str(legacy.resolve()) if item and legacy.is_dir() else '')
        current = str(self.extension_folder(browser).resolve())
        moved = bool(previous and previous != current)
        return dict(path=current, reload_required=moved or bool(item.get('extension_reload_required')),
                    previous_path=previous if moved else item.get('previous_extension_path', ''))

    def confirm_extension_reload(self, browser):
        config = self.load()
        if browser not in config.get('browsers', {}):
            raise ProtocolError('not_configured')
        item = config['browsers'][browser]
        if item.get('extension_path') != str(self.extension_folder(browser).resolve()):
            raise ProtocolError('repair_needed')
        item['extension_reload_required'] = False
        self._write(self.config_path, config)

    def _prepare_extension_folder(self, browser):
        folder = self.extension_folder(browser)
        required = ('manifest.json', 'core.js', 'background.js', 'popup.html', 'popup.js')
        if not all((folder / name).is_file() for name in required):
            if getattr(sys, 'frozen', False):
                raise ProtocolError('extension_missing')
            from .distribution import bundle_extensions
            try:
                bundle_extensions(self.resources, folder.parent)
            except (OSError, ValueError):
                raise ProtocolError('extension_missing') from None
        return folder

    def status(self, browser):
        try:
            config = self.load()
            item = config.get('browsers', {}).get(browser)
            registered = self.registry.read(browser)
            if not item: return 'not_configured'
            if registered != str(self.manifest_path(browser)) or not self.manifest_path(browser).is_file(): return 'repair_needed'
            manifest = json.loads(self.manifest_path(browser).read_text('utf-8'))
            allowed_key = 'allowed_extensions' if browser == 'firefox' else 'allowed_origins'
            allowed_value = item['extension_id'] if browser == 'firefox' else 'chrome-extension://' + item['extension_id'] + '/'
            if (manifest.get('name') != HOST_NAME or manifest.get('type') != 'stdio' or
                    manifest.get('path') != config.get('bridge_path') or manifest.get(allowed_key) != [allowed_value]):
                return 'repair_needed'
            if not Path(config.get('bridge_path', '')).is_file(): return 'repair_needed'
            if config.get('bridge_path') != str(self.bridge_path.resolve()): return 'repair_needed'
            if config.get('launch', {}).get('mode') == 'frozen' and config['launch']['path'] != str(Path(sys.executable).resolve()): return 'repair_needed'
            return 'configured'
        except (OSError, ValueError, KeyError, ProtocolError): return 'repair_needed'

    @staticmethod
    def _write(path, value):
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
        temporary.replace(path)

    def install(self, browser, extension_id=None):
        if browser not in REGISTRY_ROOTS: raise ProtocolError()
        old_config = self.load()
        old_item = old_config.get('browsers', {}).get(browser, {})
        extension_id = extension_id or old_item.get('extension_id') or self.identity(browser)
        if not valid_extension_id(browser, extension_id): raise ProtocolError('unauthorized_extension')
        if not self.bridge_path.is_file() or self.bridge_path.name != 'YTDownloaderBridge.exe': raise ProtocolError('bridge_missing')
        existing = self.registry.read(browser)
        manifest_path = self.manifest_path(browser)
        if existing and existing != str(manifest_path): raise ProtocolError('registration_conflict')
        location = self.extension_location(browser)
        folder = self._prepare_extension_folder(browser)
        self.root.mkdir(parents=True, exist_ok=True)
        config = json.loads(json.dumps(old_config)) if old_config else dict(owner=HOST_NAME, protocol=PROTOCOL, browsers={})
        config['bridge_path'] = str(self.bridge_path.resolve())
        config['launch'] = (dict(mode='frozen', path=str(Path(sys.executable).resolve())) if getattr(sys, 'frozen', False)
                            else dict(mode='source', path=str(Path(sys.executable).resolve()),
                                      root=str(Path(__file__).resolve().parents[3])))
        config['browsers'][browser] = dict(extension_id=extension_id,
            extension_path=str(folder.resolve()), extension_reload_required=location['reload_required'],
            previous_extension_path=location['previous_path'])
        manifest = dict(name=HOST_NAME, description='YTDownloader URL bridge', type='stdio', path=config['bridge_path'])
        manifest['allowed_extensions' if browser == 'firefox' else 'allowed_origins'] = (
            [extension_id] if browser == 'firefox' else ['chrome-extension://' + extension_id + '/'])
        old_manifest = manifest_path.read_bytes() if manifest_path.is_file() else None
        self._write(manifest_path, manifest)
        self._write(self.config_path, config)
        try: self.registry.write(browser, manifest_path)
        except OSError:
            if old_config: self._write(self.config_path, old_config)
            else: self.config_path.unlink(missing_ok=True)
            if old_manifest is None: manifest_path.unlink(missing_ok=True)
            else: manifest_path.write_bytes(old_manifest)
            raise
        return folder

    def remove(self, browser):
        config = self.load()
        if browser not in config.get('browsers', {}): return False
        manifest = self.manifest_path(browser)
        registered = self.registry.read(browser)
        if registered and not self.registry.remove(browser, manifest): raise ProtocolError('registration_conflict')
        config['browsers'].pop(browser)
        self._write(self.config_path, config)
        if manifest.is_file(): manifest.unlink()
        # Leave exported extensions and every other user data file intact.
        return True

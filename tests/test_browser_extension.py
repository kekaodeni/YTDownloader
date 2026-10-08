import base64
import hashlib
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'browser-extension'

@pytest.mark.parametrize('browser',['chrome','edge','firefox'])
def test_manifest_minimal_permissions_and_pinned_identity(browser):
    manifest = json.loads((ASSETS / f'manifests/{browser}.json').read_text())
    identity = json.loads((ASSETS / 'identity.json').read_text())[browser]
    assert manifest['manifest_version'] == 3
    assert set(manifest['permissions']) == {'activeTab','contextMenus','nativeMessaging'}
    for forbidden in ['host_permissions','content_scripts','externally_connectable','web_accessible_resources']:
        assert forbidden not in manifest
    if browser == 'firefox':
        assert manifest['browser_specific_settings']['gecko']['id'] == identity['id']
        assert manifest['background']['scripts'] == ['core.js','background.js']
        assert manifest['browser_specific_settings']['gecko']['data_collection_permissions']['required'] == ['none']
    else:
        digest = hashlib.sha256(base64.b64decode(manifest['key'])).digest()[:16].hex()
        assert ''.join(chr(ord('a')+int(c,16)) for c in digest) == identity['id']
        assert manifest['background'] == {'service_worker':'background.js'}

def test_extension_and_desktop_translation_keys_complete():
    locales = list((ASSETS / 'shared/_locales').glob('*/messages.json'))
    assert len(locales) == 10
    keys = None
    for path in locales:
        messages = json.loads(path.read_text('utf-8'))
        keys = keys or set(messages)
        assert set(messages) == keys
        assert all(row['message'].strip() for row in messages.values())
    catalog = json.loads((ROOT / 'src/yt_downloader/ui/translations.json').read_text('utf-8'))
    for key in keys:
        from yt_downloader.core.models import SUPPORTED_LOCALES
        assert set(catalog['messages']['browser.'+key]) == set(SUPPORTED_LOCALES)

def test_extension_no_remote_code_or_cookie_access():
    source = '\n'.join(p.read_text('utf-8') for p in (ASSETS / 'shared').glob('*.js'))
    for forbidden in ['fetch(', 'XMLHttpRequest', 'cookies.', 'tabs.onUpdated', 'tabs.onActivated', 'eval(', 'executeScript', 'localStorage']:
        assert forbidden not in source

import hashlib
import json
from pathlib import Path
import types

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from semver import Version

from test_update_signature import manifest, signed, key_bytes
from yt_downloader.updates.models import UpdateRelease
from yt_downloader.updates.signature import TrustedKeyring


def payload(version='0.5.0', schema=2):
    data = manifest('test')
    data['version'] = version
    data['release_url'] = f'https://github.com/kekaodeni/YTDownloader/releases/tag/v{version}'
    data['package']['name'] = f'YTDownloader-{version}-win64.zip'
    data['package']['url'] = f'https://github.com/kekaodeni/YTDownloader/releases/download/v{version}/' + data['package']['name']
    data['schema_version'] = schema
    data['minimum_auto_update_version'] = '0.4.1' if schema == 1 else '0.4.2'
    if schema == 2:
        data.update(updater_protocol=2, minimum_updater_version='0.4.2', helper_layout='internal-v1')
        data['package']['kind'] = 'standard'
    return data


def release_for(data):
    base = data['package']['url'].rsplit('/', 1)[0]
    return UpdateRelease(Version.parse(data['version']), 'v' + data['version'],
                         base + '/update-manifest.json', base + '/update-manifest.sig', data['release_url'])


def legacy_module(name):
    root = Path(__file__).parent / 'fixtures/update_v041'
    source = (root / name).read_bytes()
    provenance = json.loads((root / 'provenance.json').read_text())
    assert hashlib.sha256(source).hexdigest() == provenance['files'][name]
    module = types.ModuleType('legacy_' + name.removesuffix('.py'))
    exec(compile(source, str(root / name), 'exec'), module.__dict__)
    return module


def test_original_v041_parser_accepts_bridge_without_relaxing_fields():
    key = Ed25519PrivateKey.generate()
    ring = legacy_module('signature.py').TrustedKeyring({'test': key_bytes(key)})
    data = payload('0.4.2', 1)
    assert ring.verify(*signed(data, key), release_for(data)).version == Version.parse('0.4.2')
    data['helper_layout'] = 'legacy-root'
    with pytest.raises(ValueError, match='fields'):
        ring.verify(*signed(data, key), release_for(data))
    data = payload()
    with pytest.raises(ValueError):
        ring.verify(*signed(data, key), release_for(data))


def test_schema_two_verifies_internal_standard_package():
    key = Ed25519PrivateKey.generate()
    data = payload()
    result = TrustedKeyring({'test': key_bytes(key)}).verify(*signed(data, key), release_for(data))
    assert result.schema_version == 2
    assert result.helper_layout == 'internal-v1'
    assert result.minimum_updater_version == Version.parse('0.4.2')
    assert result.package.kind == 'standard'


def test_bridge_selects_highest_signed_compatible_release_without_latest(tmp_path):
    from yt_downloader.updates.discovery import UpdateDiscoveryService
    from yt_downloader.updates.models import UpdateCapability, UpdateState
    from yt_downloader.updates.service import UpdateService
    from yt_downloader.updates.state import UpdateStateStore
    from test_update_service import ImmediateRunner

    key = Ed25519PrivateKey.generate()
    releases, assets = [], {}
    for version in ('0.4.2', '0.5.0', '0.6.0', '0.7.0'):
        data = payload(version, 1 if version == '0.4.2' else 2)
        if version == '0.7.0':
            data['minimum_updater_version'] = '0.6.0'
        ref = release_for(data)
        raw, signature = signed(data, key)
        assets.update({ref.manifest_url: raw, ref.signature_url: signature})
        releases.append({'tag_name': ref.tag, 'html_url': ref.release_url, 'assets': [
            {'name': 'update-manifest.json', 'browser_download_url': ref.manifest_url},
            {'name': 'update-manifest.sig', 'browser_download_url': ref.signature_url},
        ]})
    calls = []
    def fetch(url):
        calls.append(url)
        assert '/releases?' in url and '/latest' not in url
        return releases
    service = UpdateService(current_version='0.4.2', discovery=UpdateDiscoveryService(fetch),
        fetch_bytes=assets.__getitem__, keyring=TrustedKeyring({'test': key_bytes(key)}),
        state_store=UpdateStateStore(tmp_path/'state.json'), downloader=None,
        staging_root=tmp_path/'staging', capability=UpdateCapability.CHECK_ONLY, runner=ImmediateRunner())
    service.check(manual=True)
    assert service.state == UpdateState.AVAILABLE
    assert str(service.manifest.version) == '0.6.0'
    assert service.state_store.load().highest_verified_version == '0.6.0'
    assert len(calls) == 1


def test_release_list_http_accepts_only_bounded_official_pagination():
    from yt_downloader.updates.http import SecureUpdateHttpClient
    class Response:
        def raise_for_status(self): pass
        def json(self): return []
        def close(self): pass
    class Session:
        def __init__(self):
            self.headers = {}; self.proxies = {}; self.cookies = type('C', (), {'clear': lambda _: None})(); self.auth = None
        def get(self, *_args, **_kwargs): return Response()
        def close(self): pass
    snapshot = type('S', (), {'mode': 'direct'})()
    client = SecureUpdateHttpClient(type('N', (), {'snapshot': lambda _: snapshot})(), session_factory=Session)
    base = 'https://api.github.com/repos/kekaodeni/YTDownloader/releases'
    assert client.get_json(base + '?per_page=100&page=1') == []
    for url in (base+'?per_page=100&page=0', base+'?per_page=100&page=21', base+'?per_page=100&page=1&token=x', base.replace('kekaodeni', 'other')):
        with pytest.raises(ValueError, match='trusted'):
            client.get_json(url)


@pytest.mark.parametrize('change', [
    {'updater_protocol': 1}, {'helper_layout': 'legacy-root'}, {'schema_version': True},
    {'minimum_updater_version': 'invalid'}, {'remote_key': 'untrusted'},
])
def test_schema_two_rejects_invalid_contract(change):
    key = Ed25519PrivateKey.generate()
    data = payload(); data.update(change)
    with pytest.raises(ValueError):
        TrustedKeyring({'test': key_bytes(key)}).verify(*signed(data, key), release_for(data))


def make_service(tmp_path, data_list, *, current='0.4.2', tamper=False):
    from test_update_service import ImmediateRunner
    from yt_downloader.updates.models import UpdateCapability
    from yt_downloader.updates.service import UpdateService
    from yt_downloader.updates.state import UpdateStateStore
    key = Ed25519PrivateKey.generate()
    refs = sorted((release_for(data) for data in data_list), key=lambda ref: ref.version, reverse=True)
    assets = {}
    for data in data_list:
        ref = release_for(data); raw, signature = signed(data, key)
        assets.update({ref.manifest_url: raw, ref.signature_url: signature})
    if tamper:
        assets[refs[0].manifest_url] += b' '
    discovery = type('D', (), {'check': lambda _, version: tuple(ref for ref in refs if ref.version > Version.parse(version))})()
    return UpdateService(current_version=current, discovery=discovery, fetch_bytes=assets.__getitem__,
        keyring=TrustedKeyring({'test': key_bytes(key)}), state_store=UpdateStateStore(tmp_path/'state.json'),
        downloader=None, staging_root=tmp_path/'staging', capability=UpdateCapability.CHECK_ONLY, runner=ImmediateRunner())


@pytest.mark.parametrize('restriction', ['protocol', 'application', 'helper'])
def test_signed_incompatible_candidate_does_not_poison_version_floor(tmp_path, restriction):
    higher = payload('0.6.0')
    higher[{'protocol': 'updater_protocol', 'application': 'minimum_auto_update_version', 'helper': 'minimum_updater_version'}[restriction]] = 3 if restriction == 'protocol' else '0.5.0'
    service = make_service(tmp_path, [payload(), higher])
    service.check(manual=True)
    assert str(service.manifest.version) == '0.5.0'
    assert service.state_store.load().highest_verified_version == '0.5.0'


def test_signed_failures_do_not_fall_back_to_an_older_release(tmp_path):
    from yt_downloader.updates.models import UpdateState
    service = make_service(tmp_path, [payload(), payload('0.6.0')], tamper=True)
    service.check(manual=True)
    assert service.state == UpdateState.FAILED
    assert service.manifest is None
    assert not service.state_store.load().highest_verified_version


def test_no_compatible_is_distinct_from_up_to_date(tmp_path):
    from yt_downloader.updates.models import UpdateState
    data = payload(); data['minimum_auto_update_version'] = '0.4.3'
    service = make_service(tmp_path, [data]); service.check(manual=True)
    assert service.state == UpdateState.NO_COMPATIBLE_UPDATE
    service = make_service(tmp_path, [], current='0.6.0'); service.check(manual=True)
    assert service.state == UpdateState.UP_TO_DATE


def test_v050_does_not_accept_schema_one_for_future_updates(tmp_path):
    from yt_downloader.updates.models import UpdateState
    service = make_service(tmp_path, [payload('0.5.1', 1)], current='0.5.0')
    service.check(manual=True)
    assert service.state == UpdateState.NO_COMPATIBLE_UPDATE


def test_discovery_pagination_filters_and_incomplete_results():
    from yt_downloader.updates.discovery import UpdateDiscoveryService
    from test_update_discovery import release
    ignored = [release('0.6.0', draft=True), release('0.7.0', prerelease=True), release('0.8.0-rc.1'), release('bad')]
    first = [release('0.4.2')] * 96 + ignored
    pages = [first, [release('0.5.1'), release('0.5.0')]]
    refs = UpdateDiscoveryService(lambda _: pages.pop(0)).check('0.4.2')
    assert [str(ref.version) for ref in refs] == ['0.5.1', '0.5.0']
    with pytest.raises(ValueError, match='incomplete'):
        UpdateDiscoveryService(lambda _: first, max_pages=1).check('0.4.2')
    with pytest.raises(TimeoutError):
        UpdateDiscoveryService(lambda _: [], deadline_seconds=-1).check('0.4.2')


def test_original_discovery_remains_pinned_to_latest_bridge():
    from test_update_discovery import release
    def fetch(url):
        assert url.endswith('/releases/latest')
        return release('0.4.2')
    result = legacy_module('discovery.py').UpdateDiscoveryService(fetch).check('0.4.1')
    assert str(result.version) == '0.4.2'

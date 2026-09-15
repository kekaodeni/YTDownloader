import pytest

from yt_downloader.updates.discovery import UpdateDiscoveryService
from yt_downloader.updates.http import SecureUpdateHttpClient


def release(version='0.4.1', *, prerelease=False, draft=False):
    base = f'https://github.com/kekaodeni/YTDownloader/releases/download/v{version}'
    return {
        'tag_name': f'v{version}', 'html_url': f'https://github.com/kekaodeni/YTDownloader/releases/tag/v{version}',
        'prerelease': prerelease, 'draft': draft,
        'assets': [
            {'name': 'update-manifest.json', 'browser_download_url': base + '/update-manifest.json'},
            {'name': 'update-manifest.sig', 'browser_download_url': base + '/update-manifest.sig'},
        ],
    }


def test_discovers_new_stable_release_with_exact_manifest_assets():
    service = UpdateDiscoveryService(lambda _url: release())
    found = service.check('0.4.0')
    assert str(found.version) == '0.4.1'
    assert found.tag == 'v0.4.1'
    assert found.manifest_url.endswith('/v0.4.1/update-manifest.json')
    assert found.signature_url.endswith('/v0.4.1/update-manifest.sig')


@pytest.mark.parametrize('payload', [release('0.4.0'), release('0.4.1', prerelease=True), release('0.4.1', draft=True)])
def test_ignores_current_prerelease_and_draft(payload):
    assert UpdateDiscoveryService(lambda _url: payload).check('0.4.0') is None


def test_rejects_missing_or_untrusted_manifest_asset_url():
    payload = release()
    payload['assets'][0]['browser_download_url'] = 'https://evil.invalid/update-manifest.json'
    with pytest.raises(ValueError, match='official release repository'):
        UpdateDiscoveryService(lambda _url: payload).check('0.4.0')


def test_discovery_http_uses_proxy_without_netrc_cookies_or_credentials():
    class Response:
        status_code = 200
        def json(self): return release()
        def raise_for_status(self): return None
        def close(self): self.closed = True
    class Session:
        def __init__(self): self.headers = {}; self.proxies = {}; self.cookies = type('C', (), {'clear': lambda self: None})(); self.auth = 'old'
        def get(self, url, **kwargs): self.call = (url, kwargs); return Response()
        def close(self): self.closed = True
    session = Session()
    snapshot = type('S', (), {'mode': 'system', 'detected_proxies': {'https': 'http://127.0.0.1:23333'}, 'custom_proxy_url': ''})()
    policy = type('P', (), {'snapshot': lambda self: snapshot})()
    client = SecureUpdateHttpClient(policy, session_factory=lambda: session)
    assert client.get_json('https://api.github.com/repos/kekaodeni/YTDownloader/releases/latest')['tag_name'] == 'v0.4.1'
    assert session.trust_env is False
    assert session.auth is None
    assert session.proxies == snapshot.detected_proxies
    assert 'Authorization' not in session.headers and 'Cookie' not in session.headers
    assert session.call[1]['allow_redirects'] is False
def test_update_metadata_bytes_are_bounded_and_use_release_asset_redirect_policy():
    class Response:
        status_code = 200
        headers = {}
        def __init__(self): self.closed = False
        def iter_content(self, _size): yield b'abc'; yield b'def'
        def raise_for_status(self): pass
        def close(self): self.closed = True
    response = Response()
    class Session:
        def __init__(self): self.headers={}; self.proxies={}; self.cookies=type('C',(),{'clear':lambda self:None})(); self.auth=None
        def get(self, *_args, **_kwargs): return response
        def close(self): pass
    snapshot=type('S',(),{'mode':'direct','detected_proxies':{},'custom_proxy_url':''})()
    policy=type('P',(),{'snapshot':lambda self:snapshot})()
    client = SecureUpdateHttpClient(policy, session_factory=Session)
    url = 'https://github.com/kekaodeni/YTDownloader/releases/download/v0.4.1/update-manifest.json'
    assert client.get_bytes(url, max_bytes=6) == b'abcdef'
    with pytest.raises(ValueError, match='large'):
        client.get_bytes(url, max_bytes=5)

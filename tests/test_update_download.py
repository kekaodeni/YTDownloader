import hashlib
from pathlib import Path
import threading

import pytest
from semver import Version

from yt_downloader.updates.download import UpdatePackageDownloader
from yt_downloader.updates.models import UpdateManifest, UpdatePackage
from yt_downloader.updates.http import SecureUpdateHttpClient


def manifest(data: bytes, *, declared_size=None):
    package = UpdatePackage(
        'YTDownloader-0.4.1-win64.zip',
        'https://github.com/kekaodeni/YTDownloader-releases/releases/download/v0.4.1/YTDownloader-0.4.1-win64.zip',
        len(data) if declared_size is None else declared_size, 300, hashlib.sha256(data).hexdigest(),
    )
    return UpdateManifest(Version.parse('0.4.1'), 'now', Version.parse('0.4.0'), 1, 'key', 'zh', 'en', 'release', package)


class Response:
    def __init__(self, chunks): self.chunks = chunks; self.closed = False
    def iter_content(self, _size): yield from self.chunks
    def close(self): self.closed = True


def test_download_uses_signed_length_without_content_length_and_verifies_hash(tmp_path):
    data = b'valid signed package'
    response = Response([data[:5], data[5:]])
    calls = []
    downloader = UpdatePackageDownloader(
        lambda url, timeout: (calls.append((url, timeout)), response)[1],
        free_space=lambda _path: 10_000,
    )
    progress = []
    verified = downloader.download(manifest(data), tmp_path, progress.append, threading.Event(), backup_size=100, margin=100)
    assert verified.path.read_bytes() == data
    assert calls[0][1] == (10, 30)
    assert progress[-1] == (len(data), len(data))
    assert response.closed


def test_download_rejects_oversize_and_cleans_only_its_transaction(tmp_path):
    keep = tmp_path / 'keep.txt'; keep.write_text('keep')
    response = Response([b'12345', b'too much'])
    downloader = UpdatePackageDownloader(lambda *_args: response, free_space=lambda _path: 10_000)
    with pytest.raises(ValueError, match='signed size'):
        downloader.download(manifest(b'12345'), tmp_path, lambda *_: None, threading.Event(), backup_size=0, margin=0)
    assert keep.read_text() == 'keep'
    assert not list(tmp_path.glob('update-*'))


def test_disk_budget_includes_zip_candidate_backup_and_margin(tmp_path):
    data = b'12345'
    downloader = UpdatePackageDownloader(lambda *_args: Response([data]), free_space=lambda _path: 409)
    with pytest.raises(OSError, match='space'):
        downloader.download(manifest(data), tmp_path, lambda *_: None, threading.Event(), backup_size=100, margin=10)


def test_stream_redirects_are_https_bounded_and_official():
    class R(Response):
        def __init__(self, status, location=None): super().__init__([b'ok']); self.status_code=status; self.headers={'Location': location} if location else {}
        def raise_for_status(self): return None
    responses=[R(302,'https://release-assets.githubusercontent.com/asset'),R(200)]
    class S:
        def __init__(self): self.headers={};self.proxies={};self.cookies=type('C',(),{'clear':lambda self:None})();self.auth=None;self.calls=[]
        def get(self,url,**kw): self.calls.append((url,kw)); return responses.pop(0)
        def close(self): pass
    session=S(); snap=type('S',(),{'mode':'direct','detected_proxies':{},'custom_proxy_url':''})(); policy=type('P',(),{'snapshot':lambda self:snap})()
    stream=SecureUpdateHttpClient(policy,session_factory=lambda:session).open_stream(manifest(b'ok').package.url,(10,30))
    assert b''.join(stream.iter_content(10))==b'ok';stream.close()
    assert len(session.calls)==2 and all(call[1]['allow_redirects'] is False for call in session.calls)
    responses[:]=[R(302,'http://evil.invalid/asset')]
    with pytest.raises(ValueError,match='redirect'):
        SecureUpdateHttpClient(policy,session_factory=lambda:session).open_stream(manifest(b'ok').package.url,(10,30))

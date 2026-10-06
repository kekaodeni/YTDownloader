from dataclasses import replace
import threading

import pytest
from yt_dlp.utils import DownloadError

from test_download_service import FakeYDL, _request
from yt_downloader.core.errors import AppError
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.media_resolver import MediaResolver
from yt_downloader.services.media_errors import classify_download_error


@pytest.mark.parametrize('message', ['Got error: 4654082 bytes read, 25967030 more expected. Giving up after 5 retries',
                                   'IncompleteRead(4654082 bytes read)', 'connection reset',
                                   'remote end closed connection', 'premature EOF'])
def test_incomplete_read_is_retryable_network_error(message):
    assert classify_download_error(message) == ('DOWNLOAD_INTERRUPTED', '下载连接中断，请重试。')


def test_retry_refreshes_transient_formats_and_preserves_collection_cover(tmp_path, monkeypatch):
    original = _request(tmp_path)
    original = replace(original, video=replace(original.video, canonical_thumbnail_url='https://example.org/cover.png'),
                       resolve_before_download=True, preferred_quality='1080p', batch_id='collection')
    fresh = []
    def fetch(self, url, *args, **kwargs):
        option = replace(original.format, format_selector=str(len(fresh) + 101))
        fresh.append(option)
        return replace(original.video, title='Wrong native title', thumbnail_url='https://example.org/wrong.png',
                       formats=(option,))
    monkeypatch.setattr(MediaResolver, 'fetch_metadata', fetch)
    service = DownloadService(ydl_factory=FakeYDL, require_tools=False, media_validator=lambda _: True)
    for request in (original, replace(original, resume_partial=True)):
        result = service.download(request, lambda _: None, threading.Event())
        assert result.resolved_media.title == original.video.title
        assert result.resolved_media.canonical_thumbnail_url == original.video.canonical_thumbnail_url
        assert FakeYDL.last_options['format'] == fresh[-1].format_selector
    assert len(fresh) == 2 and fresh[0].format_selector != fresh[1].format_selector


def test_interrupted_download_retry_preserves_partial_and_logs(tmp_path):
    class InterruptedYDL(FakeYDL):
        def download(self, urls):
            from pathlib import Path
            path = Path(self.options['final_path'])
            partial = path.with_suffix(path.suffix + '.part')
            if not partial.exists():
                partial.write_bytes(b'owned download bytes')
                self.options['logger'].warning('Got error: 4654082 bytes read, 25967030 more expected')
                raise DownloadError('Giving up after 5 retries')
            assert partial.read_bytes() == b'owned download bytes'
            assert self.options['continuedl'] and not self.options['nopart']
            path.write_bytes(partial.read_bytes() + b' continued')
            partial.unlink()
            return 0
    service = DownloadService(ydl_factory=InterruptedYDL, require_tools=False, media_validator=lambda _: True)
    request = _request(tmp_path)
    with pytest.raises(AppError) as caught:
        service.download(request, lambda _: None, threading.Event())
    assert caught.value.code == 'DOWNLOAD_INTERRUPTED'
    assert '4654082 bytes read' in caught.value.context.log_excerpt
    result = service.download(replace(request, resume_partial=True), lambda _: None, threading.Event())
    assert result.file_path.read_bytes().endswith(b' continued')

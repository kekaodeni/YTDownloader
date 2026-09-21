from contextlib import AbstractContextManager
from dataclasses import replace
import pickle

import pytest
from yt_dlp.utils import DownloadError, UnsupportedError

from yt_downloader.core.errors import AppError
from yt_downloader.services.youtube_service import YoutubeService


def media_fixture(extractor, url):
    return {
        'id': 'arbitrary-id/不依赖11位', 'extractor': extractor, 'extractor_key': extractor,
        'webpage_url': url, 'title': 'Fixture title', 'uploader': 'Uploader', 'channel': 'Channel',
        'duration': 61.25, 'upload_date': '20260917', 'description': 'Description',
        'thumbnail': 'https://images.example/thumb.jpg',
        'formats': [{'format_id': 'hd-main', 'url': 'https://cdn.example/media.mp4', 'ext': 'mp4',
                     'height': 720, 'vcodec': 'avc1', 'acodec': 'mp4a', 'filesize': 12345}],
        'subtitles': {'zh-CN': [{'ext': 'vtt', 'url': 'https://cdn.example/manual.vtt'}]},
        'automatic_captions': {'en': [{'ext': 'vtt', 'url': 'https://cdn.example/auto.vtt'}]},
        'playlist_id': 'list', 'playlist_title': 'List title', 'playlist_index': 2,
    }


def service_for(info, seen=None, error=None):
    class Ydl(AbstractContextManager):
        def __init__(self, options):
            self.options = options
        def __exit__(self, *args):
            pass
        def extract_info(self, url, *, download):
            assert download is False
            if seen is not None:
                seen.append((url, self.options))
            if error:
                raise error
            return info
        def sanitize_info(self, data):
            return data
    return YoutubeService(ydl_factory=Ydl, require_deno=False)


@pytest.mark.parametrize('extractor,url', [
    ('youtube', 'https://youtu.be/dQw4w9WgXcQ'),
    ('BiliBili', 'https://www.bilibili.com/video/BV1xx411c7mD'),
    ('vimeo', 'https://vimeo.com/123456'),
    ('OtherExtractor', 'https://media.example/watch/item?x=1'),
])
def test_generic_extractors_receive_url_and_map_typed_metadata(extractor, url):
    seen = []
    media = service_for(media_fixture(extractor, url), seen).fetch_metadata(url, include_thumbnail=False)
    assert seen[0][0] == url
    assert media.extractor == extractor
    assert media.extractor_key == extractor
    assert media.original_url == url and media.webpage_url == url
    assert media.media_type == 'video'
    assert media.title == 'Fixture title' and media.uploader == 'Uploader' and media.channel == 'Channel'
    assert media.upload_date == '20260917' and media.description == 'Description'
    assert media.duration == 61.25 and media.thumbnail_url
    assert media.formats[0].video_format_id == 'hd-main'
    assert media.subtitles[0].language == 'zh-CN'
    assert media.automatic_captions[0].language == 'en'
    assert media.playlist.id == 'list' and media.playlist.index == 2
    assert '/' not in media.media_key
    assert pickle.loads(pickle.dumps(media)) == media
    assert media.metadata_compatibility == ('EXPERIMENTAL' if extractor == 'OtherExtractor' else 'VERIFIED')
    assert media.download_compatibility == ('VERIFIED' if extractor.casefold() in {'youtube', 'bilibili'} else 'EXPERIMENTAL')
    assert media.compatibility == media.download_compatibility


def test_unsupported_url_has_specific_error_not_generic_parse_failure():
    url = 'https://unsupported.example/item'
    error = DownloadError('Unsupported URL: ' + url, exc_info=(UnsupportedError, UnsupportedError(url), None))
    with pytest.raises(AppError) as caught:
        service_for(None, error=error).fetch_metadata(url)
    assert caught.value.code == 'UNSUPPORTED_URL'


def test_ui_accepts_other_sites_and_uses_cross_site_media_identity(quick_window):
    url = 'https://vimeo.com/123456'
    media = service_for(media_fixture('vimeo', url)).fetch_metadata(url, include_thumbnail=False)
    page = quick_window.download_page
    page.set_clipboard_hint(url)
    assert url in page.state['clipboardHint']
    page.show_video(media)
    assert page.state['title'] == media.title and page.state['ready']
    assert not page.set_thumbnail(replace(media, extractor='Other').media_key, b'invalid')
    assert '解析已验证' in page.state['compatibilityHint']
    assert '下载兼容性仍属实验性' in page.state['compatibilityHint']
    page.show_video(replace(media, compatibility='EXPERIMENTAL', metadata_compatibility='EXPERIMENTAL',
                             download_compatibility='EXPERIMENTAL'))
    assert '尚未经过' in page.state['compatibilityHint']


def test_generic_media_thumbnail_applies_by_safe_key_and_never_by_extractor_id(quick_window):
    from scripts.verify_quick_ui import sample_video
    media = service_for(media_fixture('vimeo', 'https://vimeo.com/123')).fetch_metadata('https://vimeo.com/123', include_thumbnail=False)
    page = quick_window.download_page
    page.show_video(media)
    assert not page.set_thumbnail(media.video_id, sample_video().thumbnail_bytes)
    assert page.set_thumbnail(media.media_key, sample_video().thumbnail_bytes)
    assert page.state['thumbnail']


def test_metadata_does_not_require_javascript_runtime_for_other_sites():
    resolver = service_for(media_fixture('vimeo', 'https://vimeo.com/123'))
    resolver.require_deno = True
    resolver.deno_path = None
    assert resolver.fetch_metadata('https://vimeo.com/123', include_thumbnail=False).formats


def test_download_and_history_reuse_successful_input_not_a_different_canonical_page():
    original = 'https://player.vimeo.com/video/76979871'
    data = media_fixture('vimeo', 'https://vimeo.com/76979871')
    result = service_for(data).fetch_metadata(original, include_thumbnail=False)
    assert result.webpage_url == 'https://vimeo.com/76979871'
    assert result.original_url == original
    assert result.url == original

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


def test_media_resolver_passes_canonical_douyin_url_to_ytdlp():
    from yt_downloader.services.media_resolver import MediaResolver

    raw_url = 'https://www.douyin.com/jingxuan?modal_id=7685632626505820153'
    canonical = 'https://www.douyin.com/video/7685632626505820153'
    seen = []

    class Ydl(AbstractContextManager):
        def __init__(self, options):
            self.options = options
        def __exit__(self, *args):
            pass
        def extract_info(self, url, *, download):
            assert download is False
            seen.append(url)
            return media_fixture('Douyin', canonical)
        def sanitize_info(self, data):
            return data

    MediaResolver(ydl_factory=Ydl, require_deno=False).fetch_metadata(raw_url, include_thumbnail=False)

    assert seen == [canonical]


def test_media_resolver_passes_canonical_soop_url_to_ytdlp():
    from yt_downloader.services.media_resolver import MediaResolver

    raw_url = 'https://vod.sooplive.com/player/207618639/catch?from=share#player'
    canonical = 'https://vod.sooplive.com/player/207618639?from=share#player'
    seen = []

    class Ydl(AbstractContextManager):
        def __init__(self, options):
            self.options = options
        def __exit__(self, *args):
            pass
        def extract_info(self, url, *, download):
            assert download is False
            seen.append(url)
            return media_fixture('soop', canonical)
        def sanitize_info(self, data):
            return data

    media = MediaResolver(ydl_factory=Ydl, require_deno=False).fetch_metadata(
        raw_url, include_thumbnail=False)

    assert seen == [canonical]
    assert media.url == canonical
    assert media.original_url == raw_url


def test_soop_catch_unknown_codec_hls_format_survives_into_download_request():
    from pathlib import Path

    from yt_downloader.core.models import DownloadRequest
    from yt_downloader.services.download_options import media_options
    from yt_downloader.services.download_options import prepare_request
    from yt_downloader.services.media_resolver import MediaResolver

    raw_url = 'https://vod.sooplive.com/player/207147181/catch'
    canonical = 'https://vod.sooplive.com/player/207147181'
    native_format = {
        'format_id': 'hls', 'ext': 'mp4', 'protocol': 'm3u8_native',
        'dynamic_range': 'SDR', 'url': 'https://media.example/video/manifest.m3u8',
    }
    info = {
        '_type': 'video', 'extractor': 'soop', 'extractor_key': 'AfreecaTV',
        'id': '1788846066249480', 'title': 'SOOP Catch', 'webpage_url': canonical,
        'formats': [native_format],
    }

    class Ydl(AbstractContextManager):
        def __init__(self, options):
            self.options = options
        def __exit__(self, *args):
            pass
        def extract_info(self, url, *, download):
            assert download is False
            assert url == canonical
            return info
        def sanitize_info(self, data):
            return data

    media = MediaResolver(ydl_factory=Ydl, require_deno=False).fetch_metadata(
        raw_url, include_thumbnail=False)

    assert len(media.formats) == 1
    assert media.formats[0].video_format_id == 'hls'
    assert media.formats[0].format_selector == 'hls'
    assert media.formats[0].vcodec == media.formats[0].acodec == 'unknown'
    assert media.url == canonical
    assert media.original_url == raw_url
    assert media.video_id == info['id']

    request = prepare_request(DownloadRequest(
        task_id='soop-catch', video=media, format=media.formats[0],
        output_directory=Path('out'), filename_stem='soop-catch',
    ))
    assert request.video.url == canonical
    assert media_options(request)['format'] == 'hls'


def test_clip_request_uses_native_ytdlp_section_range_and_rejects_invalid_times():
    from pathlib import Path

    from yt_downloader.core.models import DownloadRequest, FormatOption, ResolvedMedia
    from yt_downloader.services.download_options import media_options, prepare_request
    from yt_downloader.services.video_sections import parse_clip_time, validate_clip

    media = ResolvedMedia('id', 'https://example.test/video', 'title', 'uploader', 420, None, None, (),
                          extractor_key='Youtube')
    option = FormatOption('720p', 720, 30, 'avc1', 'mp4a', 'mp4', 'mp4', 'v+a', 100, True, 'v', 'a')
    request = DownloadRequest('task', media, option, Path('.'), 'clip',
                              clip_enabled=True, clip_start=parse_clip_time('03:15'),
                              clip_end=parse_clip_time('00:05:40'))
    prepared = prepare_request(request)
    ranges = media_options(prepared)['download_ranges']
    assert list(ranges({}, None)) == [{'start_time': 195, 'end_time': 340}]

    with pytest.raises(ValueError):
        validate_clip(True, 340, 195, 420)
    with pytest.raises(ValueError):
        validate_clip(True, 0, 421, 420)


@pytest.mark.parametrize(('value', 'seconds'), [('3:15', 195), ('00:03:15', 195), ('1:02:03', 3723)])
def test_clip_time_parser_supports_mmss_and_hhmmss(value, seconds):
    from yt_downloader.services.video_sections import parse_clip_time
    assert parse_clip_time(value) == seconds


@pytest.mark.parametrize('value', ['', '-1:00', '1:60', '1:02:60', '1:2:03:04', 'abc'])
def test_clip_time_parser_rejects_invalid_clock_values(value):
    from yt_downloader.services.video_sections import parse_clip_time
    with pytest.raises(ValueError):
        parse_clip_time(value)


@pytest.mark.parametrize(('options', 'metadata', 'chapters'), [
    ({'embed_metadata': True}, True, False),
    ({'embed_chapters': True}, False, True),
    ({'embed_metadata': True, 'embed_chapters': True}, True, True),
])
def test_postprocessing_metadata_and_chapters_are_explicit_and_independent(options, metadata, chapters):
    from pathlib import Path

    from yt_downloader.core.models import DownloadRequest, FormatOption, ResolvedMedia
    from yt_downloader.services.download_options import media_options

    media = ResolvedMedia('id', 'https://example.test/video', 'title', 'uploader', 420, None, None, (),
                          extractor_key='Youtube')
    option = FormatOption('720p', 720, 30, 'avc1', 'mp4a', 'mp4', 'mp4', 'v+a', 100, True, 'v', 'a')
    request = DownloadRequest('task', media, option, Path('.'), 'clip', **options)
    actual = media_options(request)
    assert actual.get('addmetadata', False) is metadata
    assert actual['addchapters'] is chapters
    assert 'recodevideo' not in actual


def test_postprocessing_uses_ffmpeg_native_remux_and_sponsor_mark_only():
    from pathlib import Path

    from yt_downloader.core.models import DownloadRequest, FormatOption, ResolvedMedia
    from yt_downloader.services.download_options import media_options, prepare_request

    media = ResolvedMedia('id', 'https://youtube.com/watch?v=id', 'title', 'uploader', 420, None, None, (),
                          extractor_key='Youtube')
    option = FormatOption('720p', 720, 30, 'avc1', 'mp4a', 'mp4', 'mp4', 'v+a', 100, True, 'v', 'a')
    request = prepare_request(DownloadRequest('task', media, option, Path('.'), 'clip',
                                               remux_container='mkv', sponsorblock_mark=True))
    actual = media_options(request)
    assert actual['remuxvideo'] == 'mkv'
    assert actual['sponsorblock_mark'] == {'sponsor'}
    assert actual['addchapters'] is True
    assert 'recodevideo' not in actual


@pytest.mark.parametrize('probe_error', [None, TimeoutError('probe timeout'), OSError('probe unavailable')])
def test_single_unknown_soop_hls_format_uses_probe_once_and_keeps_raw_metadata(probe_error):
    from yt_downloader.services.media_resolver import MediaResolver

    url = 'https://vod.sooplive.com/player/207147181/catch'
    info = {
        '_type': 'video', 'extractor': 'soop', 'extractor_key': 'AfreecaTV',
        'id': 'native-id', 'title': 'SOOP Catch',
        'formats': [{'format_id': 'hls', 'protocol': 'm3u8_native', 'ext': 'mp4',
                     'width': None, 'height': None, 'fps': None, 'url': 'https://media.example/stream.m3u8'}],
    }
    class Ydl(AbstractContextManager):
        def __init__(self, _options): pass
        def __exit__(self, *args): pass
        def extract_info(self, _url, *, download):
            assert download is False
            return info
        def sanitize_info(self, data): return data
    class Probe:
        calls = []
        def probe_stream(self, stream_url, *, http_headers, timeout):
            self.calls.append((stream_url, http_headers, timeout))
            if probe_error:
                raise probe_error
            return {'width': 1080, 'height': 1920, 'avg_frame_rate': '60000/1001',
                    'codec_name': 'h264'}
    probe = Probe()

    media = MediaResolver(ydl_factory=Ydl, ffmpeg_service=probe, require_deno=False).fetch_metadata(
        url, include_thumbnail=False)

    assert len(probe.calls) == 1
    option = media.formats[0]
    assert option.width is option.height is option.fps is None
    assert (option.detected_width, option.detected_height) == (
        (None, None) if probe_error else (1080, 1920))
    if probe_error:
        assert option.detected_fps is None
    else:
        assert option.detected_fps == pytest.approx(60000 / 1001)
    assert option.display_metadata_source == ('original' if probe_error else 'ffprobe')
    assert option.label == ('原始画质' if probe_error else '1080p 60 FPS 竖屏')
    assert info['formats'][0]['width'] is None and info['formats'][0]['height'] is None


def test_soop_native_dimensions_skip_ffprobe():
    from yt_downloader.services.media_resolver import MediaResolver

    url = 'https://vod.sooplive.com/player/205280431/catch'
    info = {'_type': 'video', 'extractor': 'soop', 'extractor_key': 'AfreecaTV',
            'formats': [
                {'format_id': '1080P', 'protocol': 'm3u8_native', 'width': 1080,
                 'height': 1920, 'vcodec': 'avc1', 'url': 'https://media.example/a.m3u8'},
                {'format_id': '720P', 'protocol': 'm3u8_native', 'width': 720,
                 'height': 1280, 'vcodec': 'avc1', 'url': 'https://media.example/b.m3u8'},
                {'format_id': '540P', 'protocol': 'm3u8_native', 'width': 540,
                 'height': 960, 'vcodec': 'avc1', 'url': 'https://media.example/c.m3u8'},
            ]}
    class Ydl(AbstractContextManager):
        def __init__(self, _options): pass
        def __exit__(self, *args): pass
        def extract_info(self, _url, *, download): return info
        def sanitize_info(self, data): return data
    class Probe:
        def probe_stream(self, *_args, **_kwargs): raise AssertionError('native dimensions must skip ffprobe')

    media = MediaResolver(ydl_factory=Ydl, ffmpeg_service=Probe(), require_deno=False).fetch_metadata(
        url, include_thumbnail=False)
    assert [item.label for item in media.formats] == ['1080p 竖屏', '720p 竖屏', '540p 竖屏']
    assert media.formats[0].display_metadata_source == 'yt-dlp'


def test_generic_native_direct_media_uses_probe_without_mutating_raw_metadata():
    from yt_downloader.services.media_resolver import MediaResolver
    info = {'_type': 'video', 'extractor_key': 'Generic', 'formats': [
        {'format_id': 'direct', 'url': 'https://cdn.example/stream.mp4', 'protocol': 'https',
         'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none', 'width': None, 'height': None,
         'http_headers': {'User-Agent': 'fixture', 'Cookie': 'must-not-leak'}}]}
    class Ydl(AbstractContextManager):
        def __init__(self, _options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, _url, *, download): return info
        def sanitize_info(self, data): return data
    class Probe:
        calls = []
        def probe_stream(self, url, *, http_headers, timeout):
            self.calls.append((url, http_headers, timeout))
            return {'width': 1920, 'height': 1080, 'fps': 30}
    probe = Probe()
    resolver = MediaResolver(ydl_factory=Ydl, ffmpeg_service=probe, require_deno=False)
    media = resolver.fetch_metadata('https://generic.example/watch/1', include_thumbnail=False)
    resolver.fetch_metadata('https://generic.example/watch/1', include_thumbnail=False)
    assert len(probe.calls) == 1
    assert probe.calls[0][1] == {'User-Agent': 'fixture'}
    assert probe.calls[0][2] == 8
    option = media.formats[0]
    assert (option.width, option.height) == (None, None)
    assert (option.detected_width, option.detected_height) == (1920, 1080)
    assert option.display_metadata_source == 'ffprobe'
    assert info['formats'][0]['width'] is None and info['formats'][0]['height'] is None


def test_soop_unresolved_sample_dimensions_keep_raw_fields_and_show_portrait_label():
    from yt_downloader.services.media_resolver import MediaResolver
    info = {'_type': 'video', 'extractor_key': 'AfreecaTV', 'formats': [
        {'format_id': 'catch-hls', 'protocol': 'm3u8_native', 'ext': 'mp4', 'vcodec': 'unknown',
         'url': 'https://cdn.example/catch.m3u8', 'width': None, 'height': None, 'fps': None}]}
    class Ydl(AbstractContextManager):
        def __init__(self, _options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, _url, *, download): return info
        def sanitize_info(self, data): return data
    class Probe:
        def probe_stream(self, *_args, **_kwargs): return {'width': 406, 'height': 720, 'fps': 24}
    media = MediaResolver(ydl_factory=Ydl, ffmpeg_service=Probe(), require_deno=False).fetch_metadata(
        'https://vod.sooplive.com/player/207147181/catch', include_thumbnail=False)
    option = media.formats[0]
    assert option.label == '406p 竖屏'
    assert option.width is option.height is option.fps is None
    assert (option.detected_width, option.detected_height, option.detected_fps) == (406, 720, 24)
    assert info['formats'][0]['width'] is None and info['formats'][0]['height'] is None


@pytest.mark.parametrize('media_format', [
    {'format_id': 'native', 'url': 'https://cdn.example/v.mp4', 'protocol': 'https',
     'vcodec': 'avc1', 'width': 1280, 'height': 720},
    {'format_id': 'semantic', 'url': 'https://cdn.example/v.mp4', 'protocol': 'https',
     'vcodec': 'avc1', 'quality': 116},
    {'format_id': 'semantic-hdr', 'url': 'https://cdn.example/v.mp4', 'protocol': 'https',
     'vcodec': 'avc1', 'dynamic_range': 'HDR10'},
    {'format_id': 'semantic-sdr', 'url': 'https://cdn.example/v.mp4', 'protocol': 'https',
     'vcodec': 'avc1', 'dynamic_range': 'SDR'},
    {'format_id': 'page', 'url': 'https://www.example/watch/1', 'protocol': 'https', 'vcodec': 'avc1'},
    {'format_id': 'drm', 'url': 'https://cdn.example/v.mp4', 'protocol': 'https',
     'vcodec': 'avc1', 'has_drm': True},
    {'format_id': 'audio', 'url': 'https://cdn.example/a.m4a', 'protocol': 'https', 'vcodec': 'none'},
])
def test_generic_probe_eligibility_skips_sufficient_or_unsafe_formats(media_format):
    from yt_downloader.services.media_probe import needs_media_probe
    assert not needs_media_probe(media_format)


@pytest.mark.parametrize(
    ('formats', 'expected_code'),
    [([], 'NO_FORMATS'),
     ([{'format_id': 'unknown', 'vcodec': 'none', 'acodec': 'none'}], 'APP_FORMAT_FILTER_ERROR')],
)
def test_media_resolver_distinguishes_empty_metadata_from_filtered_formats(formats, expected_code):
    from yt_downloader.services.media_resolver import MediaResolver

    info = media_fixture('OtherExtractor', 'https://media.example/watch/item')
    info['formats'] = formats

    class Ydl(AbstractContextManager):
        def __init__(self, options):
            self.options = options
        def __exit__(self, *args):
            pass
        def extract_info(self, url, *, download):
            return info
        def sanitize_info(self, data):
            return data

    with pytest.raises(AppError) as caught:
        MediaResolver(ydl_factory=Ydl, require_deno=False).fetch_metadata(info['webpage_url'], include_thumbnail=False)

    assert caught.value.code == expected_code


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


@pytest.mark.parametrize('cookies', [(), (object(),)])
def test_cookie_success_evidence_requires_loaded_site_cookies(cookies):
    from yt_downloader.core.models import CookieProfile
    from yt_downloader.services.media_resolver import MediaResolver

    data = media_fixture('youtube', 'https://www.youtube.com/watch?v=123')
    class CookieJar:
        def get_cookies_for_url(self, _url):
            return cookies
    class YDL:
        def __init__(self, options):
            assert options['cookiesfrombrowser'] == ('firefox',)
            self.cookiejar = CookieJar()
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def extract_info(self, _url, download):
            assert download is False
            return data
        def sanitize_info(self, info): return info

    result = MediaResolver(ydl_factory=YDL, require_deno=False, cookie_enabled=True,
                           cookie_profile=CookieProfile('youtube', 'YouTube', 'browser', browser='firefox',
                                                        domain_hint='youtube.com')) \
        .fetch_metadata('https://www.youtube.com/watch?v=123', include_thumbnail=False)
    assert result.cookie_used is bool(cookies)

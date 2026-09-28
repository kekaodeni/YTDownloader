from contextlib import AbstractContextManager
from dataclasses import replace
from types import SimpleNamespace

from yt_downloader.app import AppController
from yt_downloader.core.models import AppSettings, CodecPreference, CookieProfile, DownloadProfile
from yt_downloader.core.formats import apply_codec_preference
from yt_downloader.services.download_profiles import BUILTIN_PROFILES
from yt_downloader.services.media_resolver import MediaResolver


URL = 'https://www.bilibili.com/video/BV1Hsah6uEs3/'
COOKIE_PROFILE = CookieProfile('bili-firefox', 'Bilibili Firefox', 'browser',
                               browser='firefox', domain_hint='bilibili.com')


def _bilibili_formats():
    formats = [{'format_id': 'audio-1', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a.40.2'}]
    for height, quality in ((360, 16), (480, 32), (720, 64), (1080, 80)):
        for format_id, codec in ((f'avc-{height}', 'avc1'), (f'hevc-{height}', 'hvc1'), (f'av1-{height}', 'av01')):
            formats.append({'format_id': format_id, 'ext': 'mp4', 'width': height * 16 // 9,
                            'height': height, 'fps': 30, 'quality': quality,
                            'vcodec': codec, 'acodec': 'none'})
    return formats


def _metadata_config_for(settings, cookie_profile):
    class Gate:
        def begin(self, url):
            return url

    class MetadataProcess:
        config = None
        def start(self, _token, _url, config):
            self.config = config

    controller = AppController.__new__(AppController)
    controller.settings = settings
    controller.deno_path = None
    controller._cancel_thumbnail = lambda: None
    controller._metadata_gate = Gate()
    controller.metadata_process = MetadataProcess()
    controller.window = SimpleNamespace(
        download_page=SimpleNamespace(selected_cookie_profile=lambda _cookies: cookie_profile),
        cookies=object(),
    )
    controller.fetch_metadata(URL)
    return controller.metadata_process.config


def test_profile_does_not_change_cookie_mode_profile_or_metadata_process_config():
    settings = AppSettings(use_cookies=True, default_download_profile_id='auto')
    auto = _metadata_config_for(settings, COOKIE_PROFILE)
    av1_profile = DownloadProfile('av1-task', 'AV1 task', codec_preference='av1')
    av1_settings = replace(settings, default_download_profile_id=av1_profile.id,
                            custom_download_profiles=(av1_profile,))
    av1 = _metadata_config_for(av1_settings, COOKIE_PROFILE)

    assert settings.use_cookies is True
    assert auto.cookie_profile == av1.cookie_profile == COOKIE_PROFILE
    assert auto.proxy_mode == av1.proxy_mode
    assert auto.custom_proxy_url == av1.custom_proxy_url
    assert not hasattr(auto, 'codec_preference')
    assert not hasattr(av1, 'codec_preference')


def test_auto_and_best_raw_bilibili_formats_and_yt_dlp_parse_options_are_identical():
    raw_formats = _bilibili_formats()
    info = {'id': 'BVfixture', 'title': 'fixture', 'extractor': 'BiliBili',
            'extractor_key': 'BiliBili', 'formats': raw_formats}
    option_snapshots = []
    raw_id_snapshots = []

    class Ydl(AbstractContextManager):
        def __init__(self, options):
            self.options = options
        def __exit__(self, *args):
            return None
        def extract_info(self, _url, *, download):
            assert download is False
            option_snapshots.append(dict(self.options))
            raw_id_snapshots.append(tuple(item['format_id'] for item in info['formats']))
            return info
        def sanitize_info(self, data):
            return data

    results = []
    profiles = (*BUILTIN_PROFILES, DownloadProfile('av1-task', 'AV1 task', codec_preference='av1'))
    for _profile in profiles:
        resolver = MediaResolver(ydl_factory=Ydl, require_deno=False,
                                 cookie_profile=COOKIE_PROFILE)
        results.append(resolver.fetch_metadata(URL, include_thumbnail=False))

    stable_options = [{key: value for key, value in options.items() if key != 'logger'}
                      for options in option_snapshots]
    assert all(options == stable_options[0] for options in stable_options[1:])
    assert option_snapshots[0]['cookiesfrombrowser'] == ('firefox',)
    assert not {'format', 'format_sort', 'extractor_args'} & option_snapshots[0].keys()
    assert all(ids == raw_id_snapshots[0] for ids in raw_id_snapshots[1:])
    assert all([option.label for option in result.formats] == [option.label for option in results[0].formats]
               for result in results[1:])
    assert max(option.display_height for option in results[-1].formats) == 1080
    assert all([option.video_format_id for option in result.formats] == [
        option.video_format_id for option in results[0].formats] for result in results[1:])


def test_profile_codec_preference_is_applied_after_metadata_without_losing_quality_tiers():
    formats = _bilibili_formats()
    # The full normalizer retains all codec candidates while exposing a stable
    # Profile-independent set of semantic quality options.
    from yt_downloader.services.media_metadata import resolve_metadata
    video = resolve_metadata({'id': 'fixture', 'extractor_key': 'BiliBili', 'formats': formats}, URL)

    av1 = tuple(apply_codec_preference(option, CodecPreference.AV1) for option in video.formats)
    h264 = tuple(apply_codec_preference(option, CodecPreference.H264) for option in video.formats)

    assert [option.label for option in av1] == [option.label for option in video.formats]
    assert [option.label for option in h264] == [option.label for option in video.formats]
    assert all(option.vcodec.startswith('av01') for option in av1)
    assert all(option.vcodec.startswith('avc1') for option in h264)
    assert [option.video_format_id for option in av1] != [option.video_format_id for option in h264]

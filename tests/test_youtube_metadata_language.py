"""UI locale affects YouTube textual extraction, never download preferences."""
from contextlib import AbstractContextManager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from yt_downloader.core.models import AppSettings
from yt_downloader.services.media_resolver import MediaResolver


@pytest.mark.parametrize(('locale', 'language'), [
    ('zh-CN', 'zh-CN'), ('zh-TW', 'zh-TW'), ('en-US', 'en'), ('ja-JP', 'ja'),
    ('ko-KR', 'ko'), ('ru-RU', 'ru'), ('es-ES', 'es'), ('pt-BR', 'pt'),
    ('vi-VN', 'vi'), ('th-TH', 'th'),
])
def test_ui_locale_uses_native_youtube_lang_list(locale, language):
    from yt_downloader.services.metadata_language import youtube_metadata_options
    assert youtube_metadata_options(locale) == {'extractor_args': {'youtube': {'lang': [language]}}}


def test_metadata_language_reaches_parse_process_from_current_settings(qapp, tmp_path):
    from yt_downloader.app import AppController
    from yt_downloader.workers.request_gate import LatestRequestGate

    calls = []
    controller = AppController.__new__(AppController)
    controller.settings = AppSettings(language='zh-TW')
    controller.deno_path = None
    controller._metadata_gate = LatestRequestGate()
    controller._cancel_thumbnail = lambda: None
    controller.window = SimpleNamespace(
        download_page=SimpleNamespace(selected_cookie_profile=lambda _cookies: None),
        cookies=SimpleNamespace(update=lambda **_kwargs: None))
    controller.metadata_process = SimpleNamespace(start=lambda *args: calls.append(args))
    controller.fetch_metadata('https://www.youtube.com/watch?v=eAmLpb28Xc8')
    config = calls[-1][-1]
    assert config.metadata_language == 'zh-TW'
    controller.settings = replace(controller.settings, language='ja-JP')
    controller.fetch_metadata('https://www.youtube.com/watch?v=eAmLpb28Xc8')
    assert calls[-1][-1].metadata_language == 'ja-JP'
    assert config.metadata_language == 'zh-TW'


def test_live_ui_language_is_snapshotted_before_settings_autosave(quick_window):
    from yt_downloader.app import AppController
    from yt_downloader.workers.request_gate import LatestRequestGate
    from scripts.verify_quick_ui import sample_video

    requests, calls = [], []
    controller = AppController.__new__(AppController)
    controller.settings = quick_window.settings_page.current_settings()
    controller.window = quick_window
    controller.deno_path = None
    controller._metadata_gate = LatestRequestGate()
    controller._cancel_thumbnail = lambda: None
    controller.metadata_process = SimpleNamespace(start=lambda *args: calls.append(args))
    controller.history = SimpleNamespace(upsert=lambda _record: None)
    controller.queue = SimpleNamespace(enqueue=requests.append)
    controller._persisted_task_stages = {}
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: pytest.fail(str(error))
    # Language previews instantly; settings autosave is a separate queued step.
    quick_window.settings_page.edit('language', 'ja-JP')
    assert quick_window.i18n.currentLocale == 'ja-JP'
    assert controller.settings.language == 'zh-CN'
    controller.fetch_metadata('https://www.youtube.com/watch?v=eAmLpb28Xc8')
    assert calls[-1][-1].metadata_language == 'ja-JP'
    page = quick_window.download_page
    page.show_video(sample_video())
    page.download_requested.connect(controller.enqueue_download)
    page.requestDownload()
    assert len(requests) == 1 and requests[0].metadata_language == 'ja-JP'
    quick_window.i18n.setLanguage('en-US')
    assert requests[0].metadata_language == 'ja-JP'


@pytest.mark.parametrize('extractor', ['Youtube', 'BiliBili', 'AfreecaTV'])
def test_resolver_language_changes_only_youtube_textual_options(extractor):
    calls = []

    class Ydl(AbstractContextManager):
        def __init__(self, options): calls.append(options)
        def __exit__(self, *_args): pass
        def extract_info(self, url, download=False):
            assert download is False
            return {'id': 'language', 'title': 'Original title', 'extractor_key': extractor,
                    'formats': [{'format_id': 'v', 'url': 'https://cdn.example/video.mp4',
                                 'ext': 'mp4', 'height': 360, 'vcodec': 'avc1', 'acodec': 'mp4a'}]}
        def sanitize_info(self, info): return info

    for locale in ('', 'zh-CN'):
        MediaResolver(ydl_factory=Ydl, require_deno=False, metadata_language=locale).fetch_metadata(
            'https://example.test/video', include_thumbnail=False)
    baseline, localized = ({key: value for key, value in options.items() if key != 'logger'}
                           for options in calls)
    assert localized.pop('extractor_args') == {'youtube': {'lang': ['zh-CN']}}
    assert localized == baseline

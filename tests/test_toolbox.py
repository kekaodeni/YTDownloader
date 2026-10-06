from yt_downloader.services.media_metadata import resolve_metadata


def test_toolbox_thumbnail_metadata():
    media = resolve_metadata(dict(id='one', title='One', thumbnail='https://example.org/small.jpg', thumbnails=[
        dict(url='https://example.org/small.jpg', width=320, height=180),
        dict(url='https://example.org/large.jpg', width=1280, height=720),
        dict(url='not-a-url', width=9999, height=9999)]), 'https://example.org/video')
    assert [(t.width, t.height) for t in media.thumbnails] == [(320, 180), (1280, 720)]
    assert len(media.thumbnails) == 2


def test_toolbox_subtitle_languages():
    media = resolve_metadata(dict(id='one', subtitles={
        'zh-Hans': [dict(ext='srt', data='1\n00:00:00,000 --> 00:00:01,000\n中文\n')],
        'en': [dict(ext='vtt', url='https://example.org/en.vtt')]}), 'https://example.org/video')
    assert {track.language for track in media.subtitles} == {'zh-Hans', 'en'}
    assert media.subtitles[0].data.endswith('中文\n')


def test_toolbox_thumbnail_download(tmp_path):
    from io import BytesIO
    from PIL import Image
    from threading import Event
    from types import SimpleNamespace
    from yt_downloader.services.toolbox_service import ToolboxService, ToolRequest
    data = BytesIO()
    Image.new('RGB', (32, 18), 'blue').save(data, 'PNG')
    seen = []
    resolver = SimpleNamespace(network_policy=None, fetch_thumbnail=lambda url, cancel: (seen.append(url), data.getvalue())[1])
    media = resolve_metadata(dict(id='one', title='One', thumbnail='https://example.org/cover.png'), 'https://example.org/video')
    result = ToolboxService(resolver).execute(ToolRequest('thumbnail', media, tmp_path,
                    thumbnail_url=media.thumbnail_url), Event())
    assert seen == [media.thumbnail_url]
    assert len(result.files) == 1 and result.files[0].suffix == '.png'
    assert result.files[0].read_bytes() == data.getvalue()


def test_toolbox_subtitle_only(tmp_path):
    from threading import Event
    from yt_downloader.services.media_resolver import MediaResolver
    from yt_downloader.services.toolbox_service import ToolboxService, ToolRequest
    media = resolve_metadata(dict(id='one', title='Subtitles only', subtitles={
        'en': [dict(ext='srt', data='1\n00:00:00,000 --> 00:00:01,000\nHello\n')]}), 'https://example.org/video')
    result = ToolboxService(MediaResolver()).execute(ToolRequest('subtitles', media, tmp_path,
                                     subtitle_languages=('en',)), Event())
    assert len(result.files) == 1
    assert result.files[0].read_text(encoding='utf-8').endswith('Hello\n')
    assert not list(tmp_path.glob('*.mp4')) and not list(tmp_path.glob('*.mkv'))


def test_toolbox_manual_vs_auto_subtitles(qapp, tmp_path):
    from types import SimpleNamespace
    from yt_downloader.ui.quick_toolbox import ToolboxPresenter
    media = resolve_metadata(dict(id='one', subtitles={'en': [dict(ext='srt', data='Manual')]},
        automatic_captions={'en': [dict(ext='vtt', url='https://example.org/en.vtt')],
                            'ja': [dict(ext='vtt', url='https://example.org/ja.vtt')]}), 'https://example.org/video')
    page = ToolboxPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.show_video(media)
    assert [(row['code'], row['auto']) for row in page.state['toolSubtitleChoices']] == [('en', False)]
    page.setIncludeAuto(True)
    assert [(row['code'], row['auto']) for row in page.state['toolSubtitleChoices']] == [('en', False), ('ja', True)]


def test_toolbox_has_shared_parser_and_secondary_navigation(quick_window, qapp):
    from conftest import find_item, run_frames, click_item
    quick_window._select_page(2)
    run_frames(qapp)
    assert find_item(quick_window, 'toolboxPage').isVisible()
    assert find_item(quick_window, 'toolboxNavigation').property('count') == 2
    assert find_item(quick_window, 'toolbox-urlInput').isVisible()
    quick_window.toolbox_page.show_video(resolve_metadata(dict(id='one', title='One'), 'https://example.org/video'))
    run_frames(qapp)
    assert find_item(quick_window, 'toolbox-thumbnailPanel').isVisible()
    click_item(quick_window, find_item(quick_window, 'toolboxNav-1'))
    run_frames(qapp)
    assert find_item(quick_window, 'toolbox-subtitlePanel').isVisible()


def test_toolbox_subtitle_conversion(tmp_path):
    from threading import Event
    from yt_downloader.services.media_resolver import MediaResolver
    from yt_downloader.services.toolbox_service import ToolboxService, ToolRequest
    media = resolve_metadata(dict(id='one', title='Converted', subtitles={
        'en': [dict(ext='vtt', data='WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello conversion\n')]}), 'https://example.org/video')
    service = ToolboxService(MediaResolver())
    assert service.subtitles.ffmpeg.available
    for extension in ('srt', 'vtt', 'ass'):
        result = service.execute(ToolRequest('subtitles', media, tmp_path,
                                 subtitle_languages=('en',), subtitle_format=extension), Event())
        assert len(result.files) == 1 and result.files[0].suffix == '.' + extension
        assert 'Hello conversion' in result.files[0].read_text(encoding='utf-8')


def test_toolbox_cookie_propagation(qapp, tmp_path, monkeypatch):
    from io import BytesIO
    from threading import Event
    from yt_downloader.core.models import CookieProfile
    from yt_downloader.services.subtitle_service import SubtitleService
    from yt_downloader.services.toolbox_service import ToolRequest
    from yt_downloader.services.cookie_service import cookie_options
    cookiefile = tmp_path / 'cookies.txt'
    cookiefile.write_text('# Netscape HTTP Cookie File\n.example.org\tTRUE\t/\tFALSE\t0\tname\tvalue\n')
    profile = CookieProfile('test', 'Test', 'file', cookie_file=str(cookiefile))
    media = resolve_metadata(dict(id='one', title='One', subtitles={
        'en': [dict(ext='srt', url='https://example.org/en.srt')]}), 'https://example.org/video')
    seen = []
    class YDL:
        def __init__(self, options): seen.append(options)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def urlopen(self, url): return BytesIO(b'1\n00:00:00,000 --> 00:00:01,000\nHello\n')
        def extract_info(self, *args): raise AssertionError('No second extraction')
        def download(self, *args): raise AssertionError('No media download')
    monkeypatch.setattr('yt_downloader.services.subtitle_service.ReadOnlyCookieYoutubeDL', YDL)
    from yt_downloader.services.network_policy import NetworkPolicy
    result = SubtitleService(network_policy=NetworkPolicy('custom', 'http://127.0.0.1:8000')).download_tracks(
        ToolRequest('subtitles', media, tmp_path, subtitle_languages=('en',), cookie_profile=profile), tmp_path, Event())
    assert len(result.files) == 1 and seen[0]['proxy'] == 'http://127.0.0.1:8000'
    for key, value in cookie_options(profile).items(): assert seen[0][key] == value


def test_toolbox_errors_share_download_error_categories(tmp_path, monkeypatch):
    import pytest
    from threading import Event
    from yt_downloader.core.errors import AppError
    from yt_downloader.services.media_resolver import MediaResolver
    from yt_downloader.services.toolbox_service import ToolboxService, ToolRequest
    media = resolve_metadata(dict(id='one', title='One', subtitles={
        'en': [dict(ext='srt', url='https://example.org/en.srt')]}), 'https://example.org/video')
    class YDL:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def urlopen(self, url): raise RuntimeError('HTTP Error 403: Forbidden')
    monkeypatch.setattr('yt_downloader.services.subtitle_service.ReadOnlyCookieYoutubeDL', YDL)
    with pytest.raises(AppError) as raised:
        ToolboxService(MediaResolver()).execute(ToolRequest('subtitles', media, tmp_path, subtitle_languages=('en',)), Event())
    assert raised.value.code == 'forbidden'


def test_toolbox_formats_optional_without_changing_download_parse_contract():
    from test_generic_media import service_for
    from yt_downloader.core.errors import AppError
    import pytest
    seen = []
    service = service_for(dict(id='asset', title='Assets only',
        thumbnail='https://example.org/thumbnail.jpg',
        subtitles={'en': [dict(ext='srt', data='Subtitle')]}), seen)
    media = service.fetch_metadata('https://example.org/video', include_thumbnail=False, require_formats=False)
    assert not media.formats and media.thumbnails and media.subtitles
    assert seen[-1][1]['ignore_no_formats_error'] is True
    with pytest.raises(AppError) as error:
        service.fetch_metadata('https://example.org/video', include_thumbnail=False)
    assert error.value.code == 'NO_FORMATS'
    assert 'ignore_no_formats_error' not in seen[-1][1]


def test_toolbox_open_results_reuses_file_and_reveal_ports(qapp, tmp_path):
    from types import SimpleNamespace
    from yt_downloader.ui.quick_toolbox import ToolboxPresenter
    from yt_downloader.services.toolbox_service import ToolResult
    page = ToolboxPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    file = tmp_path / 'saved.srt'
    file.write_text('Subtitle')
    opened, revealed = [], []
    page.open_file_requested.connect(opened.append)
    page.open_folder_requested.connect(revealed.append)
    page.tool_completed(ToolResult((file,)))
    page.openResult(0)
    page.openResultFolder()
    assert opened == revealed == [str(file)]


def test_toolbox_preview_worker_delivers_actual_image_to_presenter(qapp, qtbot, tmp_path):
    from io import BytesIO
    from types import SimpleNamespace
    from PIL import Image
    from yt_downloader.ui.quick_toolbox import ToolboxPresenter
    from yt_downloader.ui.quick_images import ImageStore
    from yt_downloader.workers.toolbox_controller import ToolboxController
    data = BytesIO()
    Image.new('RGB', (32, 18), 'blue').save(data, 'PNG')
    resolver = SimpleNamespace(fetch_thumbnail=lambda url, cancel: data.getvalue())
    page = ToolboxPresenter(str(tmp_path), ImageStore())
    controller = ToolboxController(page, lambda *args, **kwargs: None,
                                   lambda: SimpleNamespace(resolver=resolver))
    page.show_video(resolve_metadata(dict(id='one', title='One',
                    thumbnail='https://example.org/thumbnail.png'), 'https://example.org/video'))
    qtbot.waitUntil(lambda: page.state['thumbnail'].startswith('image://') and not controller.is_busy)
    assert page._preview_cache[page._preview_url] == page.state['thumbnail']
    controller.shutdown()

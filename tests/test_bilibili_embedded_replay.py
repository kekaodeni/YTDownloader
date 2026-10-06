import json
from contextlib import AbstractContextManager
from pathlib import Path

from yt_downloader.services.media_metadata import resolve_metadata


FIXTURE = Path(__file__).parent / 'fixtures' / 'bilibili_embedded_replay.json'
URL = 'https://www.bilibili.com/video/BV1TiGg6kErJ/'


def replay_info():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def test_native_bilibili_replay_entries_retain_formats_and_fallback_thumbnails():
    media = resolve_metadata(replay_info(), URL)

    assert media.media_type == 'multi_video'
    assert media.collection_quality_mode == 'RESOLVED_COMMON_FORMATS'
    assert media.collection is not None and media.collection.kind == 'multi_video'
    assert media.formats == ()
    assert media.thumbnail_url == 'https://i.example.invalid/replay-p1.jpg'
    assert [entry.id for entry in media.entries] == ['BV1TiGg6kErJ_p1', 'BV1TiGg6kErJ_p2']
    assert [entry.index for entry in media.entries] == [1, 2]
    assert all(entry.url == '' and not entry.unavailable and entry.embedded for entry in media.entries)
    assert all(entry.entry_kind == 'embedded' and entry.available for entry in media.entries)
    assert all(entry.thumbnail.endswith(f'p{i}.jpg') for i, entry in enumerate(media.entries, 1))
    assert [option.label for option in media.entries[0].formats] == [
        'HDR 60 FPS', '1080p 60 FPS', '1080p', '720p', '480p', '360p']
    assert len(media.entries[0].audio_formats) == 3
    assert all('media.example.invalid' not in option.format_selector for entry in media.entries
               for option in entry.formats + entry.audio_formats)


def test_bilibili_replay_metadata_uses_native_entries_but_keeps_ordinary_lists_flat():
    class YDL(AbstractContextManager):
        def __init__(self, options):
            self.options = options
        def __exit__(self, *args):
            pass
        def extract_info(self, _url, *, download):
            assert download is False
            return replay_info()
        def sanitize_info(self, data):
            return data

    from yt_downloader.services.media_resolver import MediaResolver
    media = MediaResolver(ydl_factory=YDL, require_deno=False).fetch_metadata(URL, include_thumbnail=False)
    assert media.media_type == 'multi_video'
    # Capture the resolver option by reusing a tiny subclass with a class-level record.
    class CaptureYDL(YDL):
        last_options = None
        def __init__(self, options):
            super().__init__(options)
            type(self).last_options = options
    MediaResolver(ydl_factory=CaptureYDL, require_deno=False).fetch_metadata(URL, include_thumbnail=False)
    assert CaptureYDL.last_options['extract_flat'] is False

    class FlatYDL(YDL):
        options_seen = []
        def __init__(self, options):
            super().__init__(options)
            type(self).options_seen.append(options)
        def extract_info(self, _url, *, download):
            return {'_type': 'playlist', 'title': 'List', 'entries': [
                {'id': '1', 'title': 'One', 'url': 'https://example.org/one'}]}
    MediaResolver(ydl_factory=FlatYDL, require_deno=False).fetch_metadata(
        'https://www.bilibili.com/list/series-123', include_thumbnail=False)
    initial = next(options for options in FlatYDL.options_seen if options['noplaylist'] is False)
    assert initial['extract_flat'] == 'in_playlist'
    assert sum(options['noplaylist'] is True for options in FlatYDL.options_seen) == 0


def test_embedded_replay_uses_collection_quality_target_and_native_index(qapp, tmp_path):
    from yt_downloader.ui.quick_download import DownloadPresenter
    class Images:
        def add(self, _value):
            return ''

    media = resolve_metadata(replay_info(), URL)
    presenter = DownloadPresenter(str(tmp_path), Images())
    presenter.show_video(media)
    assert presenter.state['playlist']
    assert presenter.state['collection']
    assert '1080p 60 FPS' in presenter.state['collectionQualityLabels']
    received = []
    presenter.collection_download_requested.connect(lambda *args: received.append(args))
    q116_index = presenter.state['collectionQualityLabels'].index('1080p 60 FPS')
    presenter.selectCollectionQuality(q116_index)
    presenter.selectEntry(0, True)
    presenter.requestDownload()
    entry = received[0][1][0]
    assert entry.index == 1
    assert entry.selected_format is None
    assert entry.quality_target == '1080p 60 FPS'

    from dataclasses import replace
    from yt_downloader.core.models import DownloadRequest
    from yt_downloader.core.quality_target import choose_quality
    from yt_downloader.services.download_options import media_options
    selected = choose_quality(entry.formats, entry.quality_target)
    assert selected.label == '1080p 60 FPS'
    request = DownloadRequest('task', replace(media, url=URL), selected, tmp_path,
                              'segment', playlist_item_index=entry.index)
    assert media_options(request)['playlist_items'] == '1'


def test_bilibili_collection_child_keeps_entry_thumbnail_not_parent_cover(qapp, tmp_path):
    from types import SimpleNamespace
    from yt_downloader.app import AppController
    from yt_downloader.core.models import AppSettings
    from yt_downloader.services.history_service import HistoryRepository
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, _value): return ''
    class Queue:
        def __init__(self): self.requests = []
        def enqueue(self, request): self.requests.append(request)

    media = resolve_metadata(replay_info(), URL)
    page = DownloadPresenter(str(tmp_path), Images())
    page.show_video(media)
    queue = Queue()
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(selected_profile=None))
    controller.settings = AppSettings()
    controller.history = HistoryRepository(tmp_path / 'history.db')
    controller.queue = queue
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: (_ for _ in ()).throw(AssertionError(error))

    controller.enqueue_collection(media, (media.entries[1],))

    assert len(queue.requests) == 1
    assert queue.requests[0].video.thumbnail_url == media.entries[1].thumbnail
    assert queue.requests[0].video.thumbnail_url != media.thumbnail_url


def test_embedded_replay_qml_renders_shared_collection_controls(qapp, quick_window):
    from dataclasses import replace
    from conftest import click_item, find_item, run_frames

    media = resolve_metadata(replay_info(), URL)
    media = replace(media, thumbnail_url=None,
                    entries=tuple(replace(entry, thumbnail='') for entry in media.entries))
    quick_window.download_page.show_video(media)
    run_frames(qapp, 100)
    assert find_item(quick_window, 'collectionItems') is not None
    assert find_item(quick_window, 'collectionQualityCombo') is not None
    from PySide6.QtCore import QObject
    assert quick_window.root.findChild(QObject, 'segmentFormatCombo') is None
    select_all = find_item(quick_window, 'collectionSelectAll')
    button = find_item(quick_window, 'downloadButton')
    assert select_all.property('checkState').value == 0
    assert button.property('text') == '下载 0 个项目'
    task_list = find_item(quick_window, 'taskList')
    task_list.setProperty('contentY', -400)
    run_frames(qapp, 60)
    checkbox = find_item(quick_window, 'collectionEntryCheck-0')
    assert checkbox.property('enabled')
    click_item(quick_window, checkbox)
    run_frames(qapp, 50)
    assert quick_window.download_page.state['selectedCount'] == 1
    assert button.property('text') == '下载 1 个项目'
    title = find_item(quick_window, 'collectionEntryTitle-0')
    click_item(quick_window, title)
    run_frames(qapp, 50)
    assert quick_window.download_page.state['selectedCount'] == 0
    assert not quick_window.qml_warnings
    assert not quick_window.qml_warnings


def test_embedded_entry_without_formats_and_page_url_is_unavailable():
    info = {'_type': 'playlist', 'extractor_key': 'BiliBili', 'entries': [
        {'id': 'missing', 'title': 'Unavailable', 'url': None, 'webpage_url': None}]}
    media = resolve_metadata(info, URL)
    assert media.entries[0].unavailable
    assert not media.entries[0].formats


def test_ytdlp_multi_video_entry_without_any_url_uses_embedded_formats():
    source = replay_info()
    source['_type'] = 'multi_video'
    source['entries'][0]['webpage_url'] = None
    source['entries'][0]['url'] = None
    media = resolve_metadata(source, URL)
    assert media.media_type == 'multi_video'
    assert media.entries[0].embedded
    assert media.entries[0].url == ''
    assert not media.entries[0].unavailable
    assert media.entries[0].formats


def test_embedded_batch_request_uses_page_url_and_native_playlist_item(tmp_path):
    from types import SimpleNamespace
    from yt_downloader.app import AppController
    from yt_downloader.core.models import AppSettings
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, _value): return ''
    class History:
        def upsert(self, _record): pass
    class Queue:
        is_busy = False
        def __init__(self): self.requests = []
        def pause(self, _batch_id): pass
        def resume(self, _batch_id): pass
        def enqueue(self, request): self.requests.append(request)

    media = resolve_metadata(replay_info(), URL)
    page = DownloadPresenter(str(tmp_path), Images())
    page.show_video(media)
    page.selectEntry(0, True)
    selected = next(option for option in media.entries[0].formats if option.label == '1080p 60 FPS')
    from dataclasses import replace
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(selected_profile=None))
    controller.settings = AppSettings()
    controller.history = History()
    controller.queue = Queue()
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: (_ for _ in ()).throw(AssertionError(error))

    controller.enqueue_collection(media, (replace(media.entries[0], selected_format=selected),))

    request = controller.queue.requests[0]
    assert request.video.url == URL
    assert request.playlist_item_index == 1
    assert request.batch_id  # internal notification aggregation, no parent TaskCard
    assert request.format.format_selector
    assert request.resolve_before_download is False


def test_download_service_enables_native_playlist_selector_for_embedded_entry(tmp_path):
    import threading
    from dataclasses import replace
    from test_download_service import FakeYDL
    from yt_downloader.services.download_service import DownloadService
    from yt_downloader.core.models import DownloadRequest

    media = resolve_metadata(replay_info(), URL)
    option = next(option for option in media.entries[1].formats if option.label == '1080p 60 FPS')
    child = replace(media, video_id=media.entries[1].id, url=URL, title=media.entries[1].title,
                    duration=media.entries[1].duration, formats=media.entries[1].formats,
                    audio_formats=media.entries[1].audio_formats, entries=(), media_type='video')
    request = DownloadRequest('replay-task', child, option, tmp_path, 'replay-p2',
                              playlist_item_index=2)

    result = DownloadService(ydl_factory=FakeYDL, require_tools=False,
                             media_validator=lambda _path: True).download(
                                 request, lambda _progress: None, threading.Event())
    assert result.file_path.is_file()
    assert FakeYDL.last_options['noplaylist'] is False
    assert FakeYDL.last_options['playlist_items'] == '2'
    assert FakeYDL.last_options['format'] == option.format_selector

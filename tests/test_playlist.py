from yt_downloader.services.media_resolver import MediaResolver


def test_playlist_maps_entries_without_extracting_or_downloading_children():
    class Probe:
        calls = 0
        def probe_stream(self, *_args, **_kwargs): self.calls += 1; return {'width': 1, 'height': 1}
    probe = Probe()
    class YDL:
        def __init__(self, options):
            self.options = options
            if options['noplaylist']:
                assert options['extract_flat'] is False
            else:
                assert options['extract_flat'] == 'in_playlist'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert not download
            if self.options['noplaylist']:
                return {'id': '1', 'title': 'First', 'url': url, 'extractor_key': 'Vimeo',
                        'formats': [{'format_id': '720', 'url': 'https://cdn.example/720.mp4',
                                     'protocol': 'https', 'ext': 'mp4', 'height': 720,
                                     'width': 1280, 'vcodec': 'avc1', 'acodec': 'mp4a'}]}
            return {'_type': 'playlist', 'id': 'p', 'title': 'Playlist',
                    'formats': [{'format_id': 'collection-page', 'url': 'https://example.org/list.mp4',
                                 'protocol': 'https', 'ext': 'mp4'}],
                    'entries': [
                {'id': '1', 'title': 'First', 'url': 'https://vimeo.com/123', 'ie_key': 'Vimeo'},
                None, {'id': '3', 'title': 'Third', 'url': 'https://example.org/video'}]}
        def sanitize_info(self, info): return info
    media = MediaResolver(ydl_factory=YDL, ffmpeg_service=probe, require_deno=False).fetch_metadata('https://example.org/list', include_thumbnail=False)
    assert media.media_type == 'playlist'
    assert media.is_collection and media.collection.kind == 'playlist'
    assert media.collection.entry_count == len(media.entries) == 3
    assert len(media.entries) == 3
    assert media.entries[0].url == 'https://vimeo.com/123'
    assert media.entries[0].entry_kind == 'external' and media.entries[0].available
    assert media.entries[1].unavailable
    assert media.formats == ()
    assert media.collection_quality_formats == ()
    assert media.collection_quality_mode == 'DEFERRED_BATCH_TARGET'
    from yt_downloader.ui.quick_download import DownloadPresenter
    class Images:
        def add(self, _value): return ''
    presenter = DownloadPresenter('/tmp', Images())
    presenter.show_video(media)
    assert presenter.state['collectionQualityLabels'] == [
        '各视频最高可用', '最高 2160p', '最高 1440p',
        '最高 1080p', '最高 720p']
    assert presenter.state['collectionQuality'] == 'highest'
    presenter.selectCollectionQuality(3)
    assert presenter.state['collectionQuality'] == 'cap:1080p'
    from yt_downloader.core.models import DownloadProfile
    presenter.show_video(media, profile=DownloadProfile('fixture', 'Fixture', quality_tier='1080p'))
    assert presenter.state['collectionQuality'] == 'highest'
    assert probe.calls == 0


def test_playlist_selection_is_explicit_and_preserves_failed_placeholders(qapp, tmp_path):
    from yt_downloader.services.media_metadata import resolve_metadata
    from yt_downloader.ui.quick_download import DownloadPresenter
    class Images:
        def add(self, value): return ''
    media = resolve_metadata({'_type': 'playlist', 'title': 'List', 'entries': [
        {'title': 'One', 'url': 'https://example.org/1'}, None,
        {'title': 'Three', 'url': 'https://example.org/3'}]}, 'https://example.org/list')
    presenter = DownloadPresenter(str(tmp_path), Images())
    presenter.show_video(media)
    assert presenter.state['collection']
    assert presenter.state['collectionQualityMode'] == 'DEFERRED_BATCH_TARGET'
    assert presenter.state['collectionQualityLabels'] == [
        '各视频最高可用', '最高 2160p', '最高 1440p',
        '最高 1080p', '最高 720p']
    assert len(presenter.state['collectionQualityLabels']) == len(set(presenter.state['collectionQualityLabels']))
    assert presenter.state['collectionSelectState'] == 0
    received = []
    presenter.collection_download_requested.connect(lambda *args: received.append(args))
    presenter.requestDownload()
    assert received == []
    presenter.selectAllEntries(True)
    assert presenter.state['selectedCount'] == 2
    assert presenter.state['collectionSelectState'] == 2
    presenter.selectEntry(0, False)
    assert presenter.state['collectionSelectState'] == 1
    presenter.requestDownload()
    assert len(received) == 1
    assert [entry.index for entry in received[0][1]] == [3]
    presenter.selectAllEntries(False)
    assert presenter.state['selectedCount'] == 0
    assert presenter.state['collectionSelectState'] == 0


def test_collection_quality_menu_uses_only_real_formats_and_profile_selects_format(qapp, tmp_path):
    from dataclasses import replace
    from yt_downloader.core.models import DownloadProfile, FormatOption
    from yt_downloader.services.media_metadata import resolve_metadata
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, _value): return ''

    media = resolve_metadata({'_type': 'playlist', 'extractor_key': 'BiliBili', 'title': 'List', 'entries': [
        {'id': '1', 'title': 'One', 'formats': [
            {'format_id': '4k', 'url': 'https://cdn.example/4k.mp4', 'protocol': 'https', 'ext': 'mp4',
             'height': 2160, 'width': 3840, 'vcodec': 'avc1', 'acodec': 'mp4a'},
            {'format_id': '1080', 'url': 'https://cdn.example/1080.mp4', 'protocol': 'https', 'ext': 'mp4',
             'height': 1080, 'width': 1920, 'vcodec': 'avc1', 'acodec': 'mp4a'},
        ]}]}, 'https://www.bilibili.com/video/BV1fixture')
    profile = DownloadProfile('best', '最高质量', quality_tier='highest')
    page = DownloadPresenter(str(tmp_path), Images())
    page.show_video(media, profile=profile)

    labels = page.state['collectionQualityLabels']
    assert labels == ['2160p 4K', '1080p']
    assert '自动推荐' not in labels and '最高质量' not in labels
    assert page.state['collectionQualityIndex'] == 0
    assert page.state['collectionQuality'] == '2160p 4K'
    page.show_video(media, profile=replace(profile, quality_tier='1080p'))
    assert page.state['collectionQualityLabels'] == ['2160p 4K', '1080p']
    assert page.state['collectionQualityIndex'] == 1
    assert page.state['collectionQuality'] == '1080p'


def test_resolved_collection_quality_uses_semantic_intersection_not_first_entry(qapp, tmp_path):
    from yt_downloader.services.media_metadata import resolve_metadata
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, _value): return ''

    def raw(format_id, height):
        return {'format_id': format_id, 'url': f'https://cdn.example/{format_id}.mp4',
                'protocol': 'https', 'ext': 'mp4', 'height': height,
                'width': height * 16 // 9, 'vcodec': 'avc1', 'acodec': 'mp4a'}

    media = resolve_metadata({'_type': 'playlist', 'title': 'Resolved collection', 'entries': [
        {'id': 'one', 'title': 'One', 'formats': [raw('a-1080', 1080), raw('a-720', 720)]},
        {'id': 'two', 'title': 'Two', 'formats': [raw('b-720', 720), raw('b-480', 480)]},
    ]}, 'https://example.org/list')
    page = DownloadPresenter(str(tmp_path), Images())
    page.show_video(media)

    assert page.state['collectionQualityMode'] == 'RESOLVED_COMMON_FORMATS'
    assert page.state['collectionQualityLabels'] == ['720p']


def test_collection_child_task_is_visible_and_removed_like_an_ordinary_task(qapp, tmp_path):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, _value): return ''

    page = DownloadPresenter(str(tmp_path), Images())
    request = replace(_request(tmp_path), task_id='collection-child', batch_id='collection')
    page.add_task(request)
    assert page.tasks.get(0)['id'] == request.task_id
    page.remove_task(request.task_id)
    assert page.tasks.count == 0


def test_taskcard_uses_child_thumbnail_url_when_bytes_are_not_loaded(qapp, tmp_path):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, _value): return ''

    page = DownloadPresenter(str(tmp_path), Images())
    for task_id, thumbnail in (
            ('child-a', 'https://i.ytimg.com/vi/video-a/hqdefault.jpg'),
            ('child-b', 'https://i.ytimg.com/vi/video-b/hqdefault.jpg')):
        request = _request(tmp_path)
        video = replace(request.video, thumbnail_url=thumbnail, thumbnail_bytes=None)
        page.add_task(replace(request, task_id=task_id, video=video))

    assert page.tasks.get(0)['thumbnail'] == 'https://i.ytimg.com/vi/video-a/hqdefault.jpg'
    assert page.tasks.get(1)['thumbnail'] == 'https://i.ytimg.com/vi/video-b/hqdefault.jpg'


def test_resolved_thumbnail_upgrades_taskcard_and_late_updates_ignore_removed_task(qapp, tmp_path):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.core.models import DownloadProgress, DownloadResult, TaskStatus
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def __init__(self): self.values = []
        def add(self, value):
            self.values.append(value)
            return f'image://thumbnails/{len(self.values)}'

    images = Images()
    page = DownloadPresenter(str(tmp_path), images)
    request = _request(tmp_path)
    original = replace(request.video, thumbnail_url='https://cdn.example/entry.jpg')
    request = replace(request, task_id='thumbnail-upgrade', video=original)
    page.add_task(request)
    page.update_task(DownloadProgress(request.task_id, TaskStatus.FETCHING_METADATA,
                                     resolved_thumbnail_url='https://cdn.example/resolved.jpg'))
    assert page.tasks.get(0)['thumbnail'] == 'https://cdn.example/resolved.jpg'
    page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO))
    assert page.tasks.get(0)['thumbnail'] == 'https://cdn.example/resolved.jpg'

    resolved = replace(original, title='Resolved title', thumbnail_url='https://cdn.example/final.jpg',
                       thumbnail_bytes=b'final-thumbnail')
    page.complete_task(DownloadResult(request.task_id, tmp_path / 'done.mp4', 10, 'now',
                                       resolved_media=resolved, resolved_format=request.format))
    assert page.tasks.get(0)['thumbnail'] == 'image://thumbnails/1'
    assert images.values == [b'final-thumbnail']

    page.remove_task(request.task_id)
    page.update_task(DownloadProgress(request.task_id, TaskStatus.FETCHING_METADATA,
                                      resolved_thumbnail_url='https://cdn.example/late.jpg'))
    assert page.tasks.count == 0


def test_taskcard_keeps_normal_video_thumbnail_bytes_and_uses_placeholder_without_thumb(qapp, tmp_path):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, value): return f'image://thumbs/{value.decode()}'

    page = DownloadPresenter(str(tmp_path), Images())
    request = _request(tmp_path)
    image_video = replace(request.video, thumbnail_url='https://cdn.example/single.jpg',
                          thumbnail_bytes=b'parsed')
    page.add_task(replace(request, task_id='single-video', video=image_video))
    page.add_task(replace(request, task_id='no-thumbnail',
                          video=replace(request.video, thumbnail_url=None, thumbnail_bytes=None)))

    assert page.tasks.get(0)['thumbnail'] == 'image://thumbs/parsed'
    assert page.tasks.get(1)['thumbnail'] == ''


def test_collection_quality_target_uses_exact_then_best_at_or_below_target():
    from yt_downloader.core.quality_target import choose_quality
    from yt_downloader.core.models import FormatOption
    def option(label, height, recommended=False):
        return FormatOption(label, height, None, 'avc1', 'mp4a', 'mp4', 'mp4', 'fmt',
                            None, False, label, is_recommended=recommended)
    options = (option('1080p 60 FPS', 1080), option('1080p', 1080),
               option('720p', 720, True), option('480p', 480))
    assert choose_quality(options, '1080p') is options[1]
    assert choose_quality((options[2], options[3]), '1080p') is options[2]
    assert choose_quality(options, 'highest') is options[0]
    assert choose_quality(options, 'recommended') is options[2]


def test_resolution_cap_keeps_best_semantic_quality_and_falls_back_per_child():
    from yt_downloader.core.quality_target import choose_quality
    from yt_downloader.core.models import FormatOption
    def option(label, height, fps=30, width=None):
        return FormatOption(label, height, fps, 'avc1', 'mp4a', 'mp4', 'mp4', label,
                            None, False, label, width=width or height * 16 // 9,
                            quality_rank=height,
                            semantic_fps=fps)
    qualities = (option('2160p', 2160), option('1440p', 1440), option('1080p 60 FPS', 1080, 60),
                 option('1080p', 1080), option('720p', 720))
    only_720 = (qualities[-1],)
    assert choose_quality(only_720, 'cap:1080p').label == '720p'
    assert choose_quality(qualities, 'cap:2160p').label == '2160p'
    assert choose_quality(qualities, 'cap:1440p').label == '1440p'
    assert choose_quality(qualities, 'cap:1080p').label == '1080p 60 FPS'
    assert choose_quality(qualities, 'cap:720p').label == '720p'
    portrait = option('1080p 竖屏', 1920, width=1080)
    assert portrait.display_height == 1080
    assert choose_quality((portrait,), 'cap:1080p') is portrait


def test_deferred_child_resolves_quality_with_profile_codec_preference(tmp_path, monkeypatch):
    import threading
    from dataclasses import replace
    from test_download_service import _request, FakeYDL
    from yt_downloader.core.formats import normalize_formats
    from yt_downloader.core.models import CodecPreference, DownloadProgress
    from yt_downloader.services.download_service import DownloadService

    template = _request(tmp_path)
    options = normalize_formats([
        {'format_id': '140', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a.40.2', 'protocol': 'https'},
        {'format_id': '401', 'ext': 'mp4', 'width': 1920, 'height': 1080,
         'vcodec': 'av01.0.08M.08', 'acodec': 'none', 'protocol': 'https'},
        {'format_id': '137', 'ext': 'mp4', 'width': 1920, 'height': 1080,
         'vcodec': 'avc1.640028', 'acodec': 'none', 'protocol': 'https'},
    ])
    media = replace(template.video, formats=tuple(options), media_type='video',
                    thumbnail_url='https://cdn.example/resolved-child.jpg')
    class Resolver:
        def __init__(self, **_kwargs): pass
        def fetch_metadata(self, *_args, **_kwargs): return media
    monkeypatch.setattr('yt_downloader.services.media_resolver.MediaResolver', Resolver)
    request = replace(template, resolve_before_download=True, preferred_quality='cap:1080p',
                      codec_preference=CodecPreference.H264)
    progress = []
    DownloadService(ydl_factory=FakeYDL, require_tools=False,
                    media_validator=lambda _path: True).download(request, progress.append, threading.Event())
    assert '137' in FakeYDL.last_options['format']
    assert any(item.resolved_thumbnail_url == media.thumbnail_url for item in progress)
    assert not any(isinstance(item, DownloadProgress) and item.resolved_quality == '2160p'
                   for item in progress)


def test_batch_child_resolves_in_shared_download_service_with_policy(tmp_path, monkeypatch):
    import threading
    from dataclasses import replace
    from test_download_service import _request, FakeYDL
    from yt_downloader.services.download_service import DownloadService
    from yt_downloader.core.models import CookieProfile, TaskStatus
    from yt_downloader.services.subtitle_service import SubtitleResult
    template = _request(tmp_path)
    profile = CookieProfile('fixture', 'Fixture', 'browser', browser='firefox')
    request = replace(template, resolve_before_download=True, batch_id='batch', media_mode='audio_only',
                      subtitle_enabled=True, subtitle_languages=('en',), cookie_profile=profile)
    media = replace(template.video, audio_formats=(replace(template.format, vcodec='none'),))
    seen = []
    class Resolver:
        def __init__(self, **options): assert options['cookie_profile'] == profile
        def fetch_metadata(self, *args, **kwargs): return media
    monkeypatch.setattr('yt_downloader.services.media_resolver.MediaResolver', Resolver)
    def subtitles(self, req, path, workspace, cancel):
        assert req.subtitle_languages == ('en',)
        assert req.cookie_profile == profile
        assert req.media_mode == 'audio_only'
        return SubtitleResult(path)
    monkeypatch.setattr('yt_downloader.services.subtitle_service.SubtitleService.process', subtitles)
    result = DownloadService(ydl_factory=FakeYDL, require_tools=False, media_validator=lambda p: True).download(request, seen.append, threading.Event())
    assert result.file_path.is_file()
    assert seen[0].status == TaskStatus.FETCHING_METADATA
    assert any(item.resolved_quality for item in seen)
    assert FakeYDL.last_options['format'] == '140'
    assert FakeYDL.last_options['cookiesfrombrowser'] == ('firefox',)


def test_collection_child_cards_use_standard_task_state(qapp, tmp_path):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.ui.quick_download import DownloadPresenter
    class Images:
        def add(self, _value): return ''
    page = DownloadPresenter(str(tmp_path), Images())
    request = replace(_request(tmp_path), batch_id='legacy-collection')
    page.add_task(replace(request, task_id='child-one'))
    page.add_task(replace(request, task_id='child-two'))
    assert all(page.tasks.get(index)['id'] for index in range(page.tasks.count))
    assert not hasattr(page, 'batches')
    page.remove_task('child-one')
    assert page.tasks.count == 1 and page.tasks.get(0)['id'] == 'child-two'


def test_resolved_quality_is_published_to_standard_task_presentation(qapp, tmp_path):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.core.models import DownloadProgress, TaskStatus
    from yt_downloader.ui.quick_download import DownloadPresenter
    class Images:
        def add(self, _value): return ''
    page = DownloadPresenter(str(tmp_path), Images())
    request = replace(_request(tmp_path), batch_id='collection', resolve_before_download=True)
    page.add_task(request)
    page.update_task(DownloadProgress(request.task_id, TaskStatus.FETCHING_METADATA,
                                      resolved_quality='720p · mp4'))
    assert page.tasks.get(0)['quality'] == '720p · mp4'


def test_collection_has_no_parent_task_card_and_child_uses_taskcard(qapp, quick_window, tmp_path):
    from dataclasses import replace
    from conftest import find_item, run_frames
    from test_download_service import _request
    from PySide6.QtCore import QObject
    page = quick_window.download_page
    request = replace(_request(tmp_path), batch_id='legacy-collection')
    page.add_task(replace(request, task_id='gui-child'))
    run_frames(qapp, 100)
    assert find_item(quick_window, 'task-gui-child').isVisible()
    assert quick_window.root.findChild(QObject, 'batch-legacy-collection') is None
    assert not hasattr(page, 'batches')
    assert not quick_window.qml_warnings


def test_controller_enqueues_selected_collection_items_as_regular_tasks(qtbot, tmp_path):
    from types import SimpleNamespace
    from yt_downloader.app import AppController
    from yt_downloader.core.models import AppSettings, DownloadProfile, TaskStatus, DownloadResult
    from yt_downloader.services.media_metadata import resolve_metadata
    from yt_downloader.services.history_service import HistoryRepository
    from yt_downloader.ui.quick_download import DownloadPresenter
    from yt_downloader.workers.download_queue import DownloadQueueController
    from yt_downloader.core.errors import AppError
    class Images:
        def add(self, value): return ''
    class Service:
        requests = []
        fail = True
        def download(self, request, callback, cancel):
            self.requests.append(request)
            if self.fail and request.video.url.endswith('/2'):
                raise AppError('fixture', 'Unavailable', 'fixture')
            return DownloadResult(request.task_id, tmp_path/'file.mp4', 1, 'now')
    media = resolve_metadata({'_type': 'playlist', 'id': 'list', 'title': 'List',
                              'thumbnail': 'https://cdn.example/parent.jpg', 'entries': [
        {'title': str(i), 'url': f'https://example.org/{i}',
         'thumbnail': f'https://cdn.example/entry-{i}.jpg'} for i in range(4)]},
        'https://example.org/list')
    page = DownloadPresenter(str(tmp_path), Images())
    page.show_video(media)
    page.selectMode('audio_only')
    service = Service()
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(selected_profile=None))
    controller.settings = AppSettings(
        default_download_profile_id='fixture',
        custom_download_profiles=(DownloadProfile('fixture', 'Fixture', quality_tier='1080p',
                                                  codec_preference='h264'),))
    controller.history = HistoryRepository(tmp_path/'history.db')
    controller.queue = DownloadQueueController(service)
    controller.queue.task_queued.connect(page.add_task)
    controller.queue.task_started.connect(page.task_started)
    controller.queue.completed.connect(page.complete_task)
    controller.queue.failed.connect(lambda task, error: page.fail_task(task, TaskStatus.FAILED))
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: (_ for _ in ()).throw(AssertionError(error))
    controller.enqueue_collection(media, (media.entries[0], media.entries[2]))
    qtbot.waitUntil(lambda: not controller.queue.is_busy, timeout=3000)
    assert len(service.requests) == 2
    assert all(r.media_mode == 'audio_only' for r in service.requests)
    assert all(str(r.codec_preference) == 'h264' for r in service.requests)
    # Concurrent workers may start in either order; identity is per child.
    assert sorted(r.video.thumbnail_url for r in service.requests) == [
        'https://cdn.example/entry-0.jpg', 'https://cdn.example/entry-2.jpg']
    assert all(r.video.canonical_thumbnail_url == r.video.thumbnail_url for r in service.requests)
    assert all(r.video.collection_thumbnail_url == media.thumbnail_url for r in service.requests)
    assert all(r.video.thumbnail_url != media.thumbnail_url for r in service.requests)
    assert media.entries[0].thumbnail == 'https://cdn.example/entry-0.jpg'
    assert service.requests[0].batch_id
    assert len({request.batch_id for request in service.requests}) == 1
    assert all(r.playlist_id == 'list' for r in controller.history.list_records())


def test_embedded_collection_retry_uses_the_ordinary_task_retry_action(qapp, tmp_path):
    from dataclasses import replace
    from types import SimpleNamespace
    from test_download_service import _request
    from yt_downloader.app import AppController
    from yt_downloader.core.models import TaskStatus
    from yt_downloader.ui.quick_download import DownloadPresenter

    class Images:
        def add(self, _value): return ''
    class History:
        def __init__(self): self.statuses = []
        def update_status(self, task_id, status): self.statuses.append((task_id, status))
    class Queue:
        def __init__(self): self.requests = []
        def enqueue(self, request): self.requests.append(request)
        def task_position(self, task_id): return None

    page = DownloadPresenter(str(tmp_path), Images())
    request = replace(_request(tmp_path), task_id='embedded-failed', batch_id='', playlist_item_index=2)
    page.add_task(request)
    page.fail_task(request.task_id, TaskStatus.FAILED)
    history, queue = History(), Queue()
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page)
    controller.history = history
    controller.queue = queue
    controller._persisted_task_stages = {}
    controller.refresh_history = lambda: None

    controller._retry_task(request.task_id)

    assert queue.requests == [replace(request, resume_partial=True)]
    assert page.task_status(request.task_id) is TaskStatus.RESUMING
    assert history.statuses == [(request.task_id, TaskStatus.PENDING)]

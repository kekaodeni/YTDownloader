from yt_downloader.services.media_resolver import MediaResolver


def test_playlist_maps_entries_without_extracting_or_downloading_children():
    class YDL:
        def __init__(self, options):
            assert options['noplaylist'] is False
            assert options['extract_flat'] == 'in_playlist'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert not download
            return {'_type': 'playlist', 'id': 'p', 'title': 'Playlist', 'entries': [
                {'id': '1', 'title': 'First', 'url': 'https://vimeo.com/123', 'ie_key': 'Vimeo'},
                None, {'id': '3', 'title': 'Third', 'url': 'https://example.org/video'}]}
        def sanitize_info(self, info): return info
    media = MediaResolver(ydl_factory=YDL, require_deno=False).fetch_metadata('https://example.org/list', include_thumbnail=False)
    assert media.media_type == 'playlist'
    assert len(media.entries) == 3
    assert media.entries[0].url == 'https://vimeo.com/123'
    assert media.entries[1].unavailable
    assert media.formats == ()


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
    received = []
    presenter.batch_requested.connect(lambda *args: received.append(args))
    presenter.requestDownload()
    assert received == []
    presenter.selectAllEntries(True)
    assert presenter.state['selectedCount'] == 2
    presenter.selectEntry(0, False)
    presenter.requestDownload()
    assert len(received) == 1
    assert [entry.index for entry in received[0][1]] == [3]
    presenter.selectAllEntries(False)
    assert presenter.state['selectedCount'] == 0


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
    assert FakeYDL.last_options['format'] == '140'
    assert FakeYDL.last_options['cookiesfrombrowser'] == ('firefox',)


def test_batch_counts_and_retry_keep_successful_children(qapp, tmp_path):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.ui.quick_download import DownloadPresenter
    from yt_downloader.core.models import DownloadResult, TaskStatus
    class Images:
        def add(self, value): return ''
    page = DownloadPresenter(str(tmp_path), Images())
    request = replace(_request(tmp_path), batch_id='b', playlist_title='List')
    page.add_batch('b', request.video, 2, 'now')
    page.add_task(replace(request, task_id='ok'))
    page.add_task(replace(request, task_id='bad'))
    page.complete_task(DownloadResult('ok', tmp_path/'ok.mp4', 1, 'now'))
    page.fail_task('bad', TaskStatus.FAILED)
    batch = page.batches.get(0)
    assert batch['completed_count'] == 1 and batch['failed_count'] == 1
    assert batch['status'] == 'completed_with_errors'
    assert page.task_status('ok') == TaskStatus.COMPLETED
    assert [r.task_id for r in page.failed_batch_requests('b')] == ['bad']
    page.add_task(replace(request, task_id='bad'))
    assert page.batches.get(0)['failed_count'] == 0
    assert page.task_status('ok') == TaskStatus.COMPLETED


def test_controller_batch_enqueues_only_selected_items_and_retry_only_failed(qtbot, tmp_path):
    from types import SimpleNamespace
    from yt_downloader.app import AppController
    from yt_downloader.core.models import AppSettings, TaskStatus, DownloadResult
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
    media = resolve_metadata({'_type': 'playlist', 'id': 'list', 'title': 'List', 'entries': [
        {'title': str(i), 'url': f'https://example.org/{i}'} for i in range(4)]}, 'https://example.org/list')
    page = DownloadPresenter(str(tmp_path), Images())
    page.show_video(media)
    page.selectMode('audio_only')
    service = Service()
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(selected_profile=None))
    controller.settings = AppSettings()
    controller.history = HistoryRepository(tmp_path/'history.db')
    controller.queue = DownloadQueueController(service)
    controller.queue.task_queued.connect(page.add_task)
    controller.queue.task_started.connect(page.task_started)
    controller.queue.completed.connect(page.complete_task)
    controller.queue.failed.connect(lambda task, error: page.fail_task(task, TaskStatus.FAILED))
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: (_ for _ in ()).throw(AssertionError(error))
    controller.enqueue_batch(media, (media.entries[0], media.entries[2]))
    qtbot.waitUntil(lambda: not controller.queue.is_busy, timeout=3000)
    assert len(service.requests) == 2
    assert all(r.media_mode == 'audio_only' for r in service.requests)
    batch_id = service.requests[0].batch_id
    assert all(r.playlist_id == 'list' for r in controller.history.list_records())
    service.fail = False
    controller._batch_action(batch_id, 'retry')
    qtbot.waitUntil(lambda: not controller.queue.is_busy, timeout=3000)
    assert len(service.requests) == 3
    assert service.requests[-1].video.url.endswith('/2')
    assert page.batches.get(0)['status'] == 'completed'

from dataclasses import replace
from pathlib import Path

from test_download_service import _request
from yt_downloader.core.models import DownloadResult


def test_archive_success_record(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    archive = ArchiveRepository(tmp_path / 'history.db')
    request = _request(tmp_path)
    media = replace(request.video, extractor_key='Youtube')
    request = replace(request, video=media)
    output = tmp_path / 'video.mp4'
    output.write_bytes(b'media')
    result = DownloadResult(request.task_id, output, 5, '2026-10-06T10:00:00+08:00')
    assert archive.record_download(request, result)
    record = archive.lookup('YouTube', media.video_id, 'video')
    assert record.title == media.title
    assert record.quality_label == request.format.label
    assert record.output_path == str(output) and record.file_exists
    assert ArchiveRepository(tmp_path / 'history.db').count() == 1
    output.unlink()
    assert not archive.lookup('Youtube', media.video_id, 'video').file_exists


def _success(tmp_path, **changes):
    request = _request(tmp_path)
    request = replace(request, video=replace(request.video, extractor_key='Youtube'), **changes)
    output = tmp_path / (request.task_id + '.mp4')
    output.write_bytes(b'media')
    return request, DownloadResult(request.task_id, output, 5, '2026-10-06T10:00:00+08:00')


def test_archive_failed_not_recorded(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.core.models import TaskStatus
    archive = ArchiveRepository(tmp_path / 'history.db')
    assert not archive.record_download(*_success(tmp_path), status=TaskStatus.FAILED)
    assert archive.count() == 0


def test_archive_cancelled_not_recorded(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.core.models import TaskStatus
    archive = ArchiveRepository(tmp_path / 'history.db')
    assert not archive.record_download(*_success(tmp_path), status=TaskStatus.CANCELLED)
    assert archive.count() == 0


def test_archive_clip_does_not_mark_full_video(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    archive = ArchiveRepository(tmp_path / 'history.db')
    assert not archive.record_download(*_success(tmp_path, clip_enabled=True, clip_start=180, clip_end=300))
    assert archive.lookup('Youtube', 'dQw4w9WgXcQ') is None


def test_archive_audio_does_not_block_video(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    archive = ArchiveRepository(tmp_path / 'history.db')
    assert archive.record_download(*_success(tmp_path, media_mode='audio_only'))
    assert archive.lookup('Youtube', 'dQw4w9WgXcQ', 'audio')
    assert archive.lookup('Youtube', 'dQw4w9WgXcQ', 'video') is None


def test_archive_history_delete_preserves_archive(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.services.history_service import HistoryRepository
    from yt_downloader.core.models import HistoryRecord, TaskStatus
    history = HistoryRepository(tmp_path / 'history.db')
    archive = ArchiveRepository(tmp_path / 'history.db')
    request, result = _success(tmp_path)
    history.upsert(HistoryRecord(request.task_id, request.video.media_key, request.video.url,
                    request.video.title, result.file_path, request.format.label, 5, None,
                    TaskStatus.COMPLETED, result.completed_at))
    archive.record_download(request, result)
    history.clear_terminal()
    assert history.list_records() == [] and archive.count() == 1
    archive.clear()
    assert archive.count() == 0


def test_archive_playlist_batch_lookup(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository, canonical_identity
    archive = ArchiveRepository(tmp_path / 'history.db')
    archive.record_download(*_success(tmp_path))
    identities = [('Youtube', str(i), 'video') for i in range(1000)]
    identities.append(('youtube', 'dQw4w9WgXcQ', 'video'))
    records = archive.lookup_many(identities)
    assert list(records) == [canonical_identity('Youtube', 'dQw4w9WgXcQ')]


def test_archive_migration(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.services.history_service import HistoryRepository
    from yt_downloader.services.settings_service import SettingsService
    from yt_downloader.core.models import HistoryRecord, TaskStatus
    import json
    history = HistoryRepository(tmp_path / 'history.db')
    history.upsert(HistoryRecord('old', 'Youtube:id', 'https://youtu.be/id', 'Old',
                    tmp_path / 'old.mp4', '1080p', 123, None, TaskStatus.COMPLETED, '2026-09-01'))
    settings_path = tmp_path / 'settings.json'
    settings_path.write_text(json.dumps(dict(schema_version=7, theme='dark',
                            download_directory=str(tmp_path), language='ja-JP')), encoding='utf-8')
    archive = ArchiveRepository(tmp_path / 'history.db')
    assert archive.count() == 0  # legacy records cannot distinguish a clip from a full video
    assert HistoryRepository(tmp_path / 'history.db').get('old').title == 'Old'
    settings = SettingsService(settings_path, default_download_directory=tmp_path).load()
    assert settings.theme == 'dark' and settings.language == 'ja-JP'
    assert settings.prevent_duplicate_downloads and settings.system_notifications
    assert (tmp_path / 'history.db.pre-archive.bak').is_file()


def test_archive_parent_not_recorded(tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.services.media_metadata import resolve_metadata
    request, result = _success(tmp_path)
    parent = resolve_metadata(dict(_type='playlist', extractor_key='Youtube', id='parent', entries=[]),
                              'https://www.youtube.com/playlist?list=parent')
    archive = ArchiveRepository(tmp_path / 'history.db')
    assert not archive.record_download(replace(request, video=parent), result)


def test_archive_override_redownload(qapp, tmp_path):
    from types import SimpleNamespace
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.ui.quick_download import DownloadPresenter
    request, result = _success(tmp_path)
    archive = ArchiveRepository(tmp_path / 'history.db')
    archive.record_download(request, result)
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.configure_archive(archive, enabled=True)
    page.show_video(request.video)
    assert page.state['archiveDuplicate']
    assert result.completed_at[:10] in page.state['archiveDetail']
    received = []
    page.download_requested.connect(lambda *args: received.append(args))
    page.requestDownload()
    assert len(received) == 1
    assert received[0][0].video_id == request.video.video_id
    # No native download_archive option can silently skip the explicit action.
    from yt_downloader.services.download_options import media_options
    assert 'download_archive' not in media_options(request)


def test_v060_database_migration(tmp_path):
    test_archive_migration(tmp_path)


def test_archive_clear_requires_confirmation(qapp, tmp_path):
    from types import SimpleNamespace
    from yt_downloader.app import AppController
    from yt_downloader.services.archive_service import ArchiveRepository
    archive = ArchiveRepository(tmp_path / 'history.db')
    archive.record_download(*_success(tmp_path))
    controller = AppController.__new__(AppController)
    controller.archive = archive
    confirmations = []
    controller.window = SimpleNamespace(
        dialogs=SimpleNamespace(confirm=lambda *args: confirmations.append(args)),
        download_page=SimpleNamespace(refresh_archive=lambda: None))
    controller._refresh_archive_count = lambda: None
    controller._confirm_clear_archive()
    assert len(confirmations) == 1 and archive.count() == 1
    confirmations[0][-1](False)
    assert archive.count() == 1
    confirmations[0][-1](True)
    assert archive.count() == 0
    assert next(tmp_path.glob('*.mp4')).exists()

from dataclasses import replace

from test_download_service import _request, FakeYDL
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.media_metadata import resolve_metadata
import threading
import pytest


def test_video_only_download_selects_no_audio(tmp_path):
    request = replace(_request(tmp_path), media_mode='video_only')
    DownloadService(ydl_factory=FakeYDL, require_tools=False,
                    media_validator=lambda path: True).download(request, lambda event: None, threading.Event())
    assert FakeYDL.last_options['format'] == '137'
    assert 'merge_output_format' not in FakeYDL.last_options


@pytest.mark.parametrize('codec,extension', [('original', 'm4a'), ('mp3', 'mp3'), ('flac', 'flac'), ('opus', 'opus')])
def test_audio_download_selects_audio_and_matching_output(tmp_path, codec, extension):
    request = replace(_request(tmp_path), media_mode='audio_only', audio_codec=codec)
    result = DownloadService(ydl_factory=FakeYDL, require_tools=False,
                    media_validator=lambda path: True).download(request, lambda event: None, threading.Event())
    options = FakeYDL.last_options
    assert options['format'] == '140'
    assert result.file_path.suffix == '.' + extension
    if codec == 'original':
        assert not options.get('postprocessors')
    else:
        assert options['postprocessors'][0]['key'] == 'FFmpegExtractAudio'
        assert options['postprocessors'][0]['preferredcodec'] == codec


def test_audio_only_metadata_exposes_downloadable_typed_choices():
    media = resolve_metadata({'id': 'a', 'formats': [
        {'format_id': 'audio', 'vcodec': 'none', 'acodec': 'opus', 'ext': 'webm', 'abr': 128},
    ]}, 'https://example.org/audio')
    assert media.audio_formats[0].format_selector == 'audio'
    assert media.audio_formats[0].vcodec == 'none'


def test_video_only_metadata_retains_silent_video_streams():
    media = resolve_metadata({'formats': [
        {'format_id': 'v', 'vcodec': 'avc1', 'acodec': 'none', 'ext': 'mp4', 'height': 720},
        {'format_id': 'a', 'vcodec': 'none', 'acodec': 'mp4a', 'ext': 'm4a'},
    ]}, 'https://example.org/video')
    assert media.video_only_formats[0].format_selector == 'v'
    assert media.video_only_formats[0].acodec == 'none'


def test_mode_switching_changes_available_choices(qapp, tmp_path):
    from yt_downloader.ui.quick_download import DownloadPresenter
    class Images:
        def add(self, value):
            return ''
    presenter = DownloadPresenter(str(tmp_path), Images())
    media = replace(_request(tmp_path).video, audio_formats=(replace(_request(tmp_path).format, vcodec='none'),))
    presenter.show_video(media)
    presenter.selectMode('audio_only')
    assert presenter.state['mediaMode'] == 'audio_only'
    assert presenter.available_formats == media.audio_formats
    presenter.selectMode('video_audio')
    assert presenter.available_formats == media.formats


def test_history_migration_preserves_old_record_and_audio_settings(tmp_path):
    import sqlite3
    from test_history_repository import _record
    from yt_downloader.core.models import TaskStatus
    from yt_downloader.services.history_service import HistoryRepository
    path = tmp_path / 'history.db'
    # Exact v0.4.x schema, independent of the current repository initializer.
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE downloads (task_id TEXT PRIMARY KEY, video_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, file_path TEXT NOT NULL, quality_label TEXT NOT NULL, file_size INTEGER, thumbnail_path TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT, error_summary TEXT)')
        db.execute("INSERT INTO downloads VALUES ('old','id','https://example.org/a','Old','old.mp4','720p',10,NULL,'COMPLETED','2026',NULL,NULL)")
        db.execute('PRAGMA user_version=1')
    repo = HistoryRepository(path)
    assert repo.get('old').title == 'Old'
    assert repo.get('old').media_mode == 'video_audio'
    record = replace(_record(tmp_path, 'audio', TaskStatus.COMPLETED), media_mode='audio_only', audio_codec='opus', audio_bitrate='128', container='opus')
    repo.upsert(record)
    assert HistoryRepository(path).get('audio') == record
    backup = path.with_suffix('.db.v1.bak')
    with sqlite3.connect(backup) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert db.execute('SELECT title FROM downloads').fetchone()[0] == 'Old'


def test_failed_migration_rolls_back_all_columns_and_preserves_data(tmp_path, monkeypatch):
    import sqlite3
    from yt_downloader.services.history_service import HistoryRepository
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE downloads (task_id TEXT PRIMARY KEY, title TEXT)')
        db.execute("INSERT INTO downloads VALUES ('old', 'Keep me')")
        db.execute('PRAGMA user_version=1')
    def fail(connection):
        connection.execute("ALTER TABLE downloads ADD COLUMN media_mode TEXT")
        raise OSError('injected migration failure')
    monkeypatch.setattr(HistoryRepository, '_migrate_media_fields', staticmethod(fail))
    with pytest.raises(OSError):
        HistoryRepository(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM downloads').fetchone() == ('old', 'Keep me')
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1


@pytest.mark.parametrize('mode,types,valid', [
    ('video_only', ['video'], True), ('video_only', ['video', 'audio'], False),
    ('audio_only', ['audio'], True), ('audio_only', ['video', 'audio'], False),
    ('video_audio', ['video', 'audio'], True), ('video_audio', ['video'], False),
])
def test_final_stream_validation_matches_selected_mode(monkeypatch, mode, types, valid):
    from yt_downloader.services.ffmpeg_service import FfmpegService
    service = FfmpegService()
    monkeypatch.setattr(service, 'probe', lambda path: {'streams': [{'codec_type': kind} for kind in types]})
    assert service.has_media_streams('fixture', mode) is valid

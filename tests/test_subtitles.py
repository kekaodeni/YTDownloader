from dataclasses import replace
import pytest
from test_download_service import _request
from yt_downloader.core.models import SubtitleTrack


def test_subtitle_selection_uses_manual_before_opt_in_automatic(tmp_path):
    from yt_downloader.services.subtitle_service import select_tracks
    req = _request(tmp_path)
    media = replace(req.video,
                    subtitles=(SubtitleTrack('en', 'vtt', 'https://example.org/manual'),),
                    automatic_captions=(SubtitleTrack('ja', 'vtt', 'https://example.org/auto'),))
    req = replace(req, video=media, subtitle_enabled=True, subtitle_languages=('en', 'ja'))
    assert [track.language for track in select_tracks(req)] == ['en']
    assert [track.language for track in select_tracks(replace(req, subtitle_auto=True))] == ['en', 'ja']


def test_subtitle_failure_preserves_successful_media(tmp_path, monkeypatch):
    import threading
    from test_download_service import FakeYDL
    from yt_downloader.services.download_service import DownloadService
    from yt_downloader.services.subtitle_service import SubtitleService
    def fail(*args, **kwargs):
        raise OSError('subtitle unavailable')
    monkeypatch.setattr(SubtitleService, 'process', fail)
    request = replace(_request(tmp_path), subtitle_enabled=True, subtitle_languages=('en',))
    result = DownloadService(ydl_factory=FakeYDL, require_tools=False, media_validator=lambda path: True).download(request, lambda p: None, threading.Event())
    assert result.file_path.is_file()
    assert result.warnings


@pytest.mark.parametrize('mode,container,allowed', [('video_audio','mp4',True), ('video_only','mkv',True), ('audio_only','mp4',False), ('video_audio','webm',False)])
def test_embed_compatibility(tmp_path, mode, container, allowed):
    from yt_downloader.services.download_options import prepare_request
    req = _request(tmp_path)
    req = replace(req, media_mode=mode, format=replace(req.format, final_ext=container), subtitle_enabled=True, subtitle_embed=True)
    if allowed:
        assert prepare_request(req).subtitle_embed
    else:
        with pytest.raises(ValueError, match='字幕'):
            prepare_request(req)


def test_no_subtitles_is_not_a_media_failure(tmp_path):
    from yt_downloader.services.subtitle_service import select_tracks
    assert select_tracks(replace(_request(tmp_path), subtitle_enabled=True, subtitle_languages=('en',))) == ()


def test_subtitle_ui_preserves_explicit_embed_choice_on_incompatible_mode(qapp, tmp_path):
    from yt_downloader.ui.quick_download import DownloadPresenter
    from types import SimpleNamespace
    presenter = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda value: ''))
    presenter.show_video(replace(_request(tmp_path).video, subtitles=(SubtitleTrack('zh-Hans', 'vtt', 'https://example.org/s'),)))
    presenter.setSubtitleOption('enabled', True)
    presenter.setSubtitleOption('embed', True)
    presenter.selectMode('audio_only')
    assert not presenter.state['subtitleCanEmbed']
    assert presenter.state['subtitleEmbed']  # no silent fallback
    assert presenter.state['subtitleHint']


def test_subtitle_history_is_persisted_with_old_defaults(tmp_path):
    from test_history_repository import _record
    from yt_downloader.core.models import TaskStatus
    from yt_downloader.services.history_service import HistoryRepository
    repo = HistoryRepository(tmp_path / 'history.db')
    original = _record(tmp_path, 'old', TaskStatus.COMPLETED)
    repo.upsert(original)
    item = replace(original, task_id='sub', subtitle_languages=('zh-Hans', 'en'),
                   subtitle_format='srt', subtitle_embedded=True, subtitle_auto_used=True)
    repo.upsert(item)
    assert HistoryRepository(repo.database_path).get('sub') == item
    assert repo.get('old').subtitle_languages == ()

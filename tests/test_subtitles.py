from dataclasses import replace
import pytest
from test_download_service import _request
from yt_downloader.core.models import SubtitleTrack


def _presenter(tmp_path):
    from types import SimpleNamespace
    from yt_downloader.ui.quick_download import DownloadPresenter
    return DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda value: ''))


def test_subtitle_none_clears_effective_state_and_disables_controls(qapp, tmp_path):
    """A newly resolved media item without captions cannot inherit the prior item's state."""
    presenter = _presenter(tmp_path)
    source = _request(tmp_path).video
    captioned = replace(source, subtitles=(SubtitleTrack('en', 'vtt', 'https://example.org/manual'),))
    presenter.show_video(captioned)
    presenter.setSubtitleOption('enabled', True)
    presenter.setSubtitleOption('embed', True)
    presenter.show_video(replace(source, video_id='no-captions'))

    state = presenter.state
    assert state['subtitleCapability'] == 'NONE'
    assert not state['subtitleEnabled']
    assert not state['subtitleAuto']
    assert not state['subtitleEmbed']
    assert state['subtitleLanguages'] == []
    assert not state['subtitleCanDownload']
    assert not state['subtitleCanAuto']
    assert not state['subtitleCanFormat']
    assert not state['subtitleCanEmbed']
    assert state['subtitleHint'] == '该视频没有可用字幕。'


def test_manual_only_and_auto_only_normalize_effective_subtitle_state(qapp, tmp_path):
    presenter = _presenter(tmp_path)
    source = _request(tmp_path).video
    manual = replace(source, subtitles=(SubtitleTrack('en', 'vtt', 'https://example.org/manual'),))
    presenter.show_video(manual)
    assert presenter.state['subtitleCapability'] == 'MANUAL_ONLY'
    assert presenter.state['subtitleCanDownload']
    assert not presenter.state['subtitleCanAuto']
    presenter.setSubtitleOption('enabled', True)
    assert presenter.state['subtitleCanFormat']
    assert presenter.state['subtitleLanguages'] == ['en']

    automatic = replace(source, video_id='auto-only', automatic_captions=(
        SubtitleTrack('ja', 'vtt', 'https://example.org/auto', is_auto=True),))
    presenter.show_video(automatic)
    assert presenter.state['subtitleCapability'] == 'AUTO_ONLY'
    presenter.setSubtitleOption('enabled', True)
    assert presenter.state['subtitleAuto']
    assert presenter.state['subtitleLanguages'] == ['ja']
    assert presenter.state['subtitleCanFormat']


def test_new_parse_clears_current_media_subtitle_capability(qapp, tmp_path):
    from yt_downloader.core.models import ParseState
    presenter = _presenter(tmp_path)
    source = _request(tmp_path).video
    presenter.show_video(replace(source, subtitles=(SubtitleTrack('en', 'vtt', 'https://example.org/manual'),)))
    presenter.setSubtitleOption('enabled', True)
    presenter.set_parse_state(ParseState.RUNNING)
    assert presenter.state['subtitleCapability'] == 'NONE'
    assert not presenter.state['subtitleEnabled']
    assert presenter.state['subtitleHint'] == '该视频没有可用字幕。'
    assert presenter.state['subtitleLanguages'] == []


def test_backend_drops_subtitle_request_when_media_has_no_matching_tracks(tmp_path):
    from yt_downloader.services.download_options import media_options, prepare_request
    request = replace(_request(tmp_path), subtitle_enabled=True, subtitle_auto=True,
                      subtitle_embed=True, subtitle_languages=('en',))
    effective = prepare_request(request)
    assert not effective.subtitle_enabled
    assert not effective.subtitle_auto
    assert not effective.subtitle_embed
    assert effective.subtitle_languages == ()
    assert not ({'writesubtitles', 'writeautomaticsub', 'subtitleslangs'} & media_options(effective).keys())


def test_backend_auto_only_request_includes_auto_tracks_without_manual_opt_in(tmp_path):
    from yt_downloader.services.download_options import prepare_request
    automatic = SubtitleTrack('ja', 'vtt', 'https://example.org/auto', is_auto=True)
    request = replace(_request(tmp_path), video=replace(_request(tmp_path).video, automatic_captions=(automatic,)),
                      subtitle_enabled=True, subtitle_languages=('ja',))
    effective = prepare_request(request)
    assert effective.subtitle_enabled
    assert effective.subtitle_auto
    assert effective.subtitle_languages == ('ja',)


def test_subtitle_none_controls_are_disabled_in_the_real_qml_page(quick_window, tmp_path):
    from conftest import find_item
    page = quick_window.download_page
    page.show_video(_request(tmp_path).video)
    assert not find_item(quick_window, 'subtitleEnabled').isEnabled()
    assert not find_item(quick_window, 'subtitleAuto').isEnabled()
    assert not find_item(quick_window, 'subtitleFormat').isEnabled()
    assert not find_item(quick_window, 'subtitleEmbed').isEnabled()


def test_download_service_never_runs_subtitle_processing_without_media_tracks(tmp_path, monkeypatch):
    import threading
    from test_download_service import FakeYDL
    from yt_downloader.services.download_service import DownloadService
    from yt_downloader.services.subtitle_service import SubtitleService

    def unexpected(*args, **kwargs):
        raise AssertionError('subtitle processing must not run without tracks')

    monkeypatch.setattr(SubtitleService, 'process', unexpected)
    request = replace(_request(tmp_path), subtitle_enabled=True, subtitle_auto=True,
                      subtitle_embed=True, subtitle_languages=('en',))
    result = DownloadService(ydl_factory=FakeYDL, require_tools=False,
                             media_validator=lambda path: True).download(request, lambda p: None, threading.Event())
    assert result.file_path.is_file()


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
    request = replace(_request(tmp_path), video=replace(_request(tmp_path).video,
                      subtitles=(SubtitleTrack('en', 'vtt', 'https://example.org/manual'),)),
                      subtitle_enabled=True, subtitle_languages=('en',))
    result = DownloadService(ydl_factory=FakeYDL, require_tools=False, media_validator=lambda path: True).download(request, lambda p: None, threading.Event())
    assert result.file_path.is_file()
    assert result.warnings


@pytest.mark.parametrize('mode,container,allowed', [('video_audio','mp4',True), ('video_only','mkv',True), ('audio_only','mp4',False), ('video_audio','webm',False)])
def test_embed_compatibility(tmp_path, mode, container, allowed):
    from yt_downloader.services.download_options import prepare_request
    req = _request(tmp_path)
    req = replace(req, video=replace(req.video, subtitles=(SubtitleTrack('en', 'vtt', 'https://example.org/manual'),)),
                  media_mode=mode, format=replace(req.format, final_ext=container), subtitle_enabled=True,
                  subtitle_languages=('en',), subtitle_embed=True)
    if allowed:
        assert prepare_request(req).subtitle_embed
    else:
        with pytest.raises(ValueError, match='字幕'):
            prepare_request(req)


def test_no_subtitles_is_not_a_media_failure(tmp_path):
    from yt_downloader.services.subtitle_service import select_tracks
    assert select_tracks(replace(_request(tmp_path), subtitle_enabled=True, subtitle_languages=('en',))) == ()


def test_subtitle_ui_clears_embed_choice_on_incompatible_mode(qapp, tmp_path):
    from yt_downloader.ui.quick_download import DownloadPresenter
    from types import SimpleNamespace
    presenter = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda value: ''))
    presenter.show_video(replace(_request(tmp_path).video, subtitles=(SubtitleTrack('zh-Hans', 'vtt', 'https://example.org/s'),)))
    presenter.setSubtitleOption('enabled', True)
    presenter.setSubtitleOption('embed', True)
    presenter.selectMode('audio_only')
    assert not presenter.state['subtitleCanEmbed']
    assert not presenter.state['subtitleEmbed']
    assert '仅音频' in presenter.state['subtitleEmbedHint']


def test_subtitle_ui_reports_manual_auto_availability_and_embed_reason(qapp, tmp_path):
    from yt_downloader.ui.quick_download import DownloadPresenter
    from types import SimpleNamespace
    presenter = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda value: ''))
    video = replace(_request(tmp_path).video,
                    subtitles=(SubtitleTrack('en', 'vtt', 'https://example.org/manual'),),
                    automatic_captions=(SubtitleTrack('ja', 'vtt', 'https://example.org/auto'),))
    presenter.show_video(video)
    assert presenter.state['subtitleManualStatus'].startswith('人工字幕：可用')
    assert presenter.state['subtitleAutoStatus'].startswith('自动字幕：可用')
    presenter.setSubtitleOption('enabled', True)
    presenter.setSubtitleOption('embed', True)
    presenter.selectMode('audio_only')
    assert '仅音频' in presenter.state['subtitleEmbedHint']


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

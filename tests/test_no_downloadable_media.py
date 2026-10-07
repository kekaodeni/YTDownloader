"""Empty content is an informational result, with independent auth evidence."""
from dataclasses import replace
from types import SimpleNamespace
import pickle

import pytest
from yt_dlp.utils import DownloadError, ExtractorError
from yt_downloader.core.models import AuthState, SUPPORTED_LOCALES, ParseState
from yt_downloader.core.errors import AppError, ErrorContext
from yt_downloader.services.media_errors import classify_auth_metadata_error, classify_metadata_error
from yt_downloader.services.media_metadata import resolve_metadata
from yt_downloader.services.media_resolver import MediaResolver
from yt_downloader.services.error_actions import error_presentation
from yt_downloader.ui.quick_download import DownloadPresenter
from test_unified_cookie_auth import profile

NO_MEDIA = 'NO_DOWNLOADABLE_MEDIA'
NO_VIDEO = 'No video could be found in this tweet'


@pytest.mark.parametrize('state', [AuthState.VALID, AuthState.UNKNOWN, AuthState.NOT_APPLICABLE])
def test_x_no_video_classifies_no_downloadable_media(state):
    code, _, auth = classify_auth_metadata_error(DownloadError(NO_VIDEO), auth_state=state,
                                                 cookie_matched=True, site='X')
    assert code == NO_MEDIA
    assert auth is state


def test_x_no_video_with_valid_auth_not_cookie_invalid():
    assert classify_auth_metadata_error(DownloadError(NO_VIDEO), auth_state=AuthState.VALID,
                                        cookie_matched=True, site='X')[0] == NO_MEDIA


@pytest.mark.parametrize('message', [NO_VIDEO, 'Could not authenticate you; ' + NO_VIDEO])
def test_x_no_video_with_invalid_auth_prefers_cookie_invalid(message):
    assert classify_auth_metadata_error(DownloadError(message), auth_state=AuthState.INVALID,
                                        cookie_matched=True, site='X')[0] == 'COOKIE_INVALID'


@pytest.mark.parametrize('state', [AuthState.VALID, AuthState.UNKNOWN])
def test_x_server_failure_precedes_no_media(state):
    inner = DownloadError('Could not authenticate you')
    error = DownloadError(NO_VIDEO, exc_info=(type(inner), inner, None))
    code, _, auth = classify_auth_metadata_error(error, auth_state=state, cookie_matched=True, site='X')
    assert code == 'COOKIE_INVALID' and auth is AuthState.INVALID


@pytest.mark.parametrize(('message', 'provider'), [
    (NO_VIDEO, 'Twitter'),
    ('No video could be found in this post', 'Bluesky'),
    ('No video could be found in this post', 'Tumblr'),
    ('There is no video in this post', 'Instagram'),
    ('No media found', 'Reddit'),
    ('Post does not contain a video or audio track', 'Floatplane'),
])
def test_explicit_no_media_evidence(message, provider):
    from yt_downloader.services.media_errors import classify_no_media_evidence
    error = DownloadError(f'ERROR: [{provider.lower()}] id: {message}')
    assert classify_no_media_evidence(exception=error, extractor_key=provider) == NO_MEDIA
    assert classify_metadata_error(error)[0] == NO_MEDIA


@pytest.mark.parametrize(('message', 'expected'), [
    ('No video formats found', 'TEMPORARY_EXTRACTOR_ERROR'),
    ('API failure: No media information found', 'TEMPORARY_EXTRACTOR_ERROR'),
    ('Sign in to confirm your age; ' + NO_VIDEO, 'AUTH_REQUIRED'),
    ('Private video; ' + NO_VIDEO, 'PRIVATE_MEDIA'),
    ('Not available in your country; ' + NO_VIDEO, 'GEO_RESTRICTED'),
    ('Video has been removed; ' + NO_VIDEO, 'CONTENT_UNAVAILABLE'),
    ('Requested format is not available; ' + NO_VIDEO, 'FORMAT_UNAVAILABLE'),
    ('Connection timed out; ' + NO_VIDEO, 'NETWORK_ERROR'),
    ('[youtube] No media found', 'TEMPORARY_EXTRACTOR_ERROR'),
    ('HTTP Error 500; ' + NO_VIDEO, 'TEMPORARY_EXTRACTOR_ERROR'),
])
def test_ambiguous_or_higher_priority_failure_is_not_no_media(message, expected):
    assert classify_metadata_error(DownloadError(message))[0] == expected


def test_empty_formats_alone_not_enough_for_no_media():
    from yt_downloader.services.media_errors import classify_no_media_evidence
    info = dict(id='1', title='Existing media', extractor_key='Youtube', formats=[])
    assert classify_no_media_evidence(metadata=info) is None


@pytest.mark.parametrize('availability', ['private', 'premium_only', 'subscriber_only', 'needs_auth'])
def test_restricted_content_cannot_become_empty_media(availability):
    from yt_downloader.services.media_errors import classify_no_media_evidence
    assert classify_no_media_evidence(metadata=dict(empty_child(), availability=availability)) is None


def test_generic_invalid_auth_precedes_explicit_no_media():
    code, _, state = classify_auth_metadata_error(DownloadError('[instagram] There is no video in this post'),
                      auth_state=AuthState.INVALID, cookie_matched=True, site='Instagram')
    assert code == 'COOKIE_INVALID' and state is AuthState.INVALID


@pytest.mark.parametrize('message', ['Could not authenticate you; ' + NO_VIDEO,
                                    'Connection timed out; ' + NO_VIDEO,
                                    'Sign in to view this post; ' + NO_VIDEO])
def test_native_child_auth_or_network_failure_still_propagates(message):
    from yt_downloader.services.media_resolver import _MetadataYoutubeDL
    from yt_dlp.extractor.common import InfoExtractor
    class ChildIE(InfoExtractor):
        _VALID_URL = r'https://x\.com/test/(?P<id>\d+)'
        def _real_extract(self, _url):
            raise ExtractorError(message, expected=True)
    with _MetadataYoutubeDL(dict(quiet=True, cachedir=False)) as ydl:
        ydl.add_info_extractor(ChildIE())
        with pytest.raises(DownloadError):
            ydl.process_ie_result(dict(_type='playlist', id='list', title='List',
                extractor='test', extractor_key='Test', entries=[
                dict(_type='url', url='https://x.com/test/1', ie_key=ChildIE.ie_key())]), download=False)


def test_no_media_not_temporary_extractor_error():
    assert classify_metadata_error(DownloadError(NO_VIDEO))[0] == NO_MEDIA


def test_no_media_does_not_offer_check_update():
    title, body, actions = error_presentation(NO_MEDIA, retry_available=True)
    assert title == 'media.no_downloadable.title'
    assert body == 'media.no_downloadable.body'
    assert actions == ()


def playlist(*entries):
    return dict(_type='playlist', id='list', title='Collection', extractor_key='Generic', entries=list(entries))


def empty_child():
    # Only the metadata adapter sets this after classifying a native exception.
    return dict(id='empty', title='Text post', url='https://x.com/user/status/123',
                ie_key='Twitter', _app_no_downloadable_media=True)


def test_playlist_no_media_child_is_disabled(qapp, tmp_path):
    media = resolve_metadata(playlist(dict(id='v', url='https://example.org/video'), empty_child()),
                             'https://example.org/list')
    assert media.entries[1].no_downloadable_media and media.entries[1].unavailable
    assert pickle.loads(pickle.dumps(media)).entries[1].no_downloadable_media
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.show_video(media)
    page.selectAllEntries(True)
    assert page.state['selectedCount'] == 1
    row = page.entries.get(1)
    assert row['unavailable'] and not row['selected']
    assert row['statusKey'] == 'playlist.no_downloadable_media'
    assert '待下载时解析' not in row['detail']
    page.selectMode('audio_only')
    assert page.entries.get(1)['statusKey'] == 'playlist.no_downloadable_media'


def test_playlist_no_media_child_does_not_abort_container():
    from yt_downloader.services.media_resolver import _MetadataYoutubeDL
    from yt_dlp.extractor.common import InfoExtractor
    class ParentIE(InfoExtractor):
        _VALID_URL = r'https://example\.org/list'
        def _real_extract(self, _url):
            return self.playlist_result([
                self.url_result('https://x.com/post/video', ChildIE),
                self.url_result('https://x.com/post/text', ChildIE)], 'list', 'Collection')
    class ChildIE(InfoExtractor):
        _VALID_URL = r'https://x\.com/post/(?P<id>video|text)'
        def _real_extract(self, url):
            ident = self._match_id(url)
            if ident == 'text':
                raise ExtractorError(NO_VIDEO, expected=True)
            return dict(id=ident, title='Video', url='https://cdn.example.org/video.mp4',
                        ext='mp4', width=1280, height=720, vcodec='avc1', acodec='aac')
    with _MetadataYoutubeDL(dict(quiet=True, cachedir=False, skip_download=True)) as ydl:
        ydl.add_info_extractor(ParentIE())
        ydl.add_info_extractor(ChildIE())
        result = ydl.extract_info('https://example.org/list', download=False, ie_key=ParentIE.ie_key())
    assert len(result['entries']) == 2
    assert result['entries'][0]['url'] == 'https://cdn.example.org/video.mp4'
    assert result['entries'][1]['_app_no_downloadable_media'] is True
    media = resolve_metadata(result, 'https://example.org/list')
    assert media.entries[0].available and media.entries[1].unavailable


@pytest.mark.parametrize('info', [playlist(empty_child(), empty_child()), playlist()])
def test_playlist_all_children_no_media_returns_no_media(info):
    class Ydl:
        def __init__(self, _options): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, *_args, **_kwargs): return info
        def sanitize_info(self, value): return value
    with pytest.raises(AppError) as failure:
        MediaResolver(ydl_factory=Ydl).fetch_metadata('https://example.org/list', include_thumbnail=False)
    assert failure.value.code == NO_MEDIA


def test_unknown_playlist_placeholders_are_not_proof_of_no_media():
    from yt_downloader.services.media_errors import classify_no_media_evidence
    assert classify_no_media_evidence(metadata=playlist(None)) is None
    assert classify_no_media_evidence(metadata=playlist(dict(id='v', formats=[]))) is None


@pytest.mark.parametrize('prior', [AuthState.VALID, AuthState.UNKNOWN])
def test_no_media_auth_status_preserved(qapp, tmp_path, prior):
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.set_cookie_state((profile('x.com'),))
    page.set_url('https://x.com/post/123')
    page.setCookieEnabled(True)
    page._show_auth_state(prior, cookie_used=True)
    before = page.state['cookieAuthStatus']
    page.requestParse()
    page.set_parse_state(ParseState.RUNNING)
    page.set_cookie_parse_error(NO_MEDIA, auth_state=AuthState.UNKNOWN, cookie_used=True)
    assert page.state['cookieAuthStatus'] == before
    assert page.state['url'] == 'https://x.com/post/123'
    assert not page.state['cookieAuthInvalid']


def test_no_media_preserved_status_translates_after_language_switch(qapp, tmp_path):
    from yt_downloader.ui.localization import Translator
    translator = Translator('zh-CN')
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''), translator=translator)
    page.set_cookie_state((profile('bilibili.com'),))
    page.set_url('https://bilibili.com/video/1')
    page.setCookieEnabled(True)
    page._show_auth_state(AuthState.VALID, cookie_used=True)
    page.requestParse()
    translator.setLanguage('en-US')
    page.set_cookie_parse_error(NO_MEDIA, auth_state=AuthState.UNKNOWN, cookie_used=True)
    assert page.state['cookieAuthStatus'] == translator.text('download.cookie_valid', {'site': 'Bilibili'})


def test_no_media_info_dialog(quick_window, qapp):
    from conftest import find_item, run_frames
    from yt_downloader.ui.quick_dialogs import ErrorSession
    title, body, actions = error_presentation(NO_MEDIA, retry_available=True)
    error = AppError(NO_MEDIA, '', NO_VIDEO, ErrorContext(cookie_site='X'),
                     title_message_id=title, body_message_id=body)
    session = ErrorSession(error, 'Internal report', quick_window, actions=actions, retry_callback=lambda: None)
    session.show()
    run_frames(qapp)
    assert session.state['kind'] == 'empty_media'
    assert session.state['title'] == '没有可下载媒体'
    assert session.state['message'] == '这个帖子中没有检测到可下载的视频或音频。'
    assert session.state['errorActions'] == []
    assert not session.state['hasRetry']
    assert not find_item(quick_window, 'errorDetails').isVisible()
    assert find_item(quick_window, 'dialogCancel').isVisible()
    for locale in SUPPORTED_LOCALES:
        quick_window.i18n.setLanguage(locale)
        run_frames(qapp, 20)
        assert quick_window.i18n.validateCoverage() == []
        assert session.state['message'] == quick_window.i18n.text('media.no_downloadable.post_body')
    session.reject()


def _apply_empty_result(qapp, tmp_path):
    from yt_downloader.app import AppController
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.services.history_service import HistoryRepository
    archive = ArchiveRepository(tmp_path / 'downloads.db')
    history = HistoryRepository(tmp_path / 'downloads.db')
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.configure_archive(archive)
    page.set_url('https://x.com/post/123')
    emitted = []
    page.download_requested.connect(lambda *_: emitted.append('download'))
    page.collection_download_requested.connect(lambda *_: emitted.append('collection'))
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(update=lambda **_: None))
    controller.show_error = lambda _: None
    controller._apply_metadata_error(AppError(NO_MEDIA, '', NO_VIDEO))
    page.requestDownload()
    assert emitted == []
    return archive, history


def test_no_media_does_not_write_archive(qapp, tmp_path):
    archive, _ = _apply_empty_result(qapp, tmp_path)
    assert archive.count() == 0


def test_no_media_does_not_create_completed_history(qapp, tmp_path):
    _, history = _apply_empty_result(qapp, tmp_path)
    assert history.list_records() == []

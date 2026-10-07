"""Server auth evidence and parse-result presentation are separate contracts."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from yt_dlp.utils import DownloadError

from yt_downloader.core.errors import AppError
from yt_downloader.core.models import AuthState, SUPPORTED_LOCALES
from yt_downloader.services.auth_state import detect_auth_state
from yt_downloader.services.media_errors import classify_auth_metadata_error
from yt_downloader.services.media_resolver import MediaResolver
from yt_downloader.ui.quick_download import DownloadPresenter
from test_unified_cookie_auth import cookie, jar, profile
from test_download_service import _request


def classify(message, *, state=AuthState.UNKNOWN, matched=True, site='X'):
    return classify_auth_metadata_error(DownloadError(message), auth_state=state,
                                        cookie_matched=matched, site=site)


@pytest.mark.parametrize('message', ['Could not authenticate you', 'Authentication failed',
                                    'Invalid or expired token'])
def test_x_could_not_authenticate_is_invalid(message):
    code, _, state = classify(message)
    assert code == 'COOKIE_INVALID'
    assert state is AuthState.INVALID


@pytest.mark.parametrize('previous_state', [AuthState.UNKNOWN, AuthState.VALID])
def test_x_server_auth_failure_overrides_unexpired_cookie(previous_state):
    ydl = SimpleNamespace(cookiejar=jar(cookie('.x.com', 'auth_token', expires=2147483647)))
    state = detect_auth_state(ydl, 'https://x.com/post/1', 'Twitter', cookie_enabled=True,
                              cookie_profile=profile('x.com'))
    assert state is AuthState.UNKNOWN
    inner = DownloadError('Error(s) while querying API: Could not authenticate you')
    outer = DownloadError('Extraction failed', exc_info=(type(inner), inner, None))
    assert classify_auth_metadata_error(outer, auth_state=previous_state, cookie_matched=True,
                                        site='X')[2] is AuthState.INVALID


def test_x_server_auth_failure_promotes_cookie_invalid():
    class Ydl:
        def __init__(self, _options):
            self.cookiejar = jar(cookie('.x.com', 'auth_token', expires=2147483647))
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, *_args, **_kwargs):
            raise DownloadError('Error(s) while querying API: Could not authenticate you')
    with pytest.raises(AppError) as failure:
        MediaResolver(ydl_factory=Ydl, cookie_enabled=True, cookie_profile=profile('x.com')).fetch_metadata(
            'https://x.com/post/1', include_thumbnail=False)
    assert failure.value.code == 'COOKIE_INVALID'
    assert failure.value.context.auth_state is AuthState.INVALID


@pytest.mark.parametrize(('site', 'matched', 'message'), [
    ('YouTube', True, 'Could not authenticate you'),
    ('example.org', True, 'Authentication failed'),
    ('X', False, 'Could not authenticate you'),
    ('X', True, 'Please authenticate to view this media'),
    ('X', True, 'HTTP Error 401: Unauthorized'),
])
def test_x_auth_patterns_are_scoped_and_do_not_guess(site, matched, message):
    assert classify(message, site=site, matched=matched)[2] is AuthState.UNKNOWN


@pytest.mark.parametrize('state', [AuthState.UNKNOWN, AuthState.VALID])
def test_x_no_video_without_auth_failure_not_invalid(state):
    code, _, result = classify('No video could be found in this tweet', state=state)
    assert code != 'COOKIE_INVALID'
    assert result is state


def page_for(domain, tmp_path):
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.set_cookie_state((profile(domain),))
    page.set_url('https://' + domain + '/video')
    page.setCookieEnabled(True)
    return page


@pytest.mark.parametrize('domain', ['youtube.com', 'x.com', 'bilibili.com', 'example.org'])
@pytest.mark.parametrize(('auth', 'success', 'used', 'key', 'tone'), [
    (AuthState.VALID, True, True, 'download.cookie_valid', 'success'),
    (AuthState.VALID, False, True, 'download.cookie_valid', 'success'),
    (AuthState.INVALID, True, True, 'download.cookie_invalid', 'error'),
    (AuthState.INVALID, False, True, 'download.cookie_invalid', 'error'),
    (AuthState.UNKNOWN, True, True, 'download.cookie_used', 'success'),
    (AuthState.UNKNOWN, False, True, 'download.cookie_unknown', 'neutral'),
    (AuthState.UNKNOWN, True, False, 'download.cookie_unknown_unused', 'neutral'),
    (AuthState.UNKNOWN, False, False, 'download.cookie_unknown_unused', 'neutral'),
])
def test_cookie_presentation_matrix(qapp, tmp_path, domain, auth, success, used, key, tone):
    page = page_for(domain, tmp_path)
    media = replace(_request(tmp_path).video, url=page.state['url'], auth_state=auth, cookie_used=used)
    if success:
        page.show_video(media)
        assert media.auth_state is auth and page.video.auth_state is auth
    else:
        page.set_cookie_parse_error('TEMPORARY_EXTRACTOR_ERROR', auth_state=auth, cookie_used=used)
    assert page._cookie_status_key == key
    assert page.state['cookieAuthSeverity'] == tone
    assert page.state['cookieAuthInvalid'] is (auth is AuthState.INVALID)


def test_cookie_ui_pending(qapp, tmp_path):
    page = page_for('youtube.com', tmp_path)
    assert page._cookie_status_key == 'download.cookie_pending'
    page.requestParse()
    assert page._cookie_status_key == 'download.cookie_verifying'
    assert page.state['cookieAuthSeverity'] == 'neutral'


def test_youtube_public_success_keeps_auth_unknown(qapp, tmp_path):
    page = page_for('youtube.com', tmp_path)
    media = replace(_request(tmp_path).video, auth_state=AuthState.UNKNOWN, cookie_used=True)
    page.show_video(media)
    assert page.video.auth_state is AuthState.UNKNOWN
    assert page.state['cookieAuthStatus'] == 'YouTube Cookie：已使用 · 解析成功'


def test_youtube_fresh_cookie_invalid_regression(qapp, tmp_path):
    code, message, state = classify('Fresh cookies are needed', site='YouTube')
    page = page_for('youtube.com', tmp_path)
    page.set_cookie_parse_error(code, message, auth_state=state, cookie_used=True)
    assert state is AuthState.INVALID
    assert page.state['cookieAuthStatus'] == 'YouTube Cookie：登录失效'


def test_x_invalid_updates_toolbar_status(qapp, tmp_path):
    from yt_downloader.app import AppController
    from yt_downloader.core.errors import ErrorContext
    from yt_downloader.workers.metadata_process import _serialize_error, _deserialize_error
    page = page_for('x.com', tmp_path)
    code, message, state = classify('Could not authenticate you')
    error = _deserialize_error(_serialize_error(AppError(code, message, 'Could not authenticate you',
        ErrorContext(auth_state=state, cookie_used=True, cookie_site='X'))))
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(update=lambda **_: None))
    # Status must be corrected before the popup opens.
    seen = []
    controller.show_error = lambda _: seen.append(page.state['cookieAuthStatus'])
    controller._apply_metadata_error(error)
    assert seen == ['X Cookie：登录失效']


def test_used_successfully_translates_live_for_every_site(qapp, tmp_path):
    from yt_downloader.ui.localization import Translator
    translator = Translator('zh-CN')
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''), translator=translator)
    page.set_cookie_state((profile('example.org'),))
    page.set_url('https://example.org/video')
    page.setCookieEnabled(True)
    page.show_video(replace(_request(tmp_path).video, auth_state=AuthState.UNKNOWN, cookie_used=True))
    for locale in SUPPORTED_LOCALES:
        translator.setLanguage(locale)
        assert translator.validateCoverage() == []
        assert page.state['cookieAuthStatus'] == translator.text('download.cookie_used', {'site': page._cookie_site_name()})
        assert 'YouTube' not in page.state['cookieAuthStatus']
        assert page.state['cookieAuthSeverity'] == 'success'
        assert page.video.auth_state is AuthState.UNKNOWN


def test_invalid_toolbar_uses_error_color(quick_window, qapp):
    from conftest import find_item, run_frames
    page = quick_window.download_page
    page.set_cookie_state((profile('x.com'),))
    page.set_url('https://x.com/post/1')
    page.setCookieEnabled(True)
    page.set_cookie_parse_error('COOKIE_INVALID', auth_state=AuthState.INVALID, cookie_used=True)
    run_frames(qapp)
    assert find_item(quick_window, 'cookieAuthStatus').property('color').name().lower() == quick_window.theme.state['danger'].lower()

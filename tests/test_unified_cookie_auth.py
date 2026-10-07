"""One authentication pipeline for every routed Cookie source."""
from types import SimpleNamespace
from http.cookiejar import Cookie, CookieJar
from dataclasses import replace

from yt_downloader.core.models import AuthState, CookieProfile
from yt_downloader.services.auth_state import detect_auth_state
from yt_downloader.services.media_resolver import MediaResolver
from yt_downloader.core.errors import AppError
import pytest
from yt_dlp.utils import DownloadError


def cookie(domain, name='session', *, expires=None):
    return Cookie(0, name, 'synthetic-test-secret', None, False, domain, True,
                  domain.startswith('.'), '/', True, True, expires, expires is None, None, None, {})


def jar(*cookies):
    result = CookieJar()
    for item in cookies:
        result.set_cookie(item)
    return result


def profile(domain):
    return CookieProfile('test', 'Custom site', 'browser', browser='firefox', domain_hint=domain)


def test_auth_state_generic_profile_match():
    ydl = SimpleNamespace(cookiejar=jar(cookie('.example.org')))
    assert detect_auth_state(ydl, 'https://example.org/video', 'Generic',
                             cookie_enabled=True, cookie_profile=profile('example.org')) is AuthState.UNKNOWN


def test_x_extractor_failure_plus_invalid_auth_becomes_cookie_invalid():
    class Ydl:
        def __init__(self, options):
            self.cookiejar = jar(cookie('.x.com', 'ct0'))
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def extract_info(self, *_args, **_kwargs):
            raise DownloadError('No video could be found in this tweet')
    with pytest.raises(AppError) as failure:
        MediaResolver(ydl_factory=Ydl, cookie_enabled=True, cookie_profile=profile('x.com')).fetch_metadata(
            'https://x.com/user/status/123', include_thumbnail=False)
    assert failure.value.code == 'COOKIE_INVALID'
    assert failure.value.context.auth_state == AuthState.INVALID


def test_auth_status_never_blank_when_cookie_profile_matched(qapp):
    from yt_downloader.ui.quick_download import DownloadPresenter
    page = DownloadPresenter('', None)
    page.set_cookie_state((profile('x.com'),))
    page.set_url('https://x.com/user/status/123')
    page.setCookieEnabled(True)
    assert page.state['cookieAuthStatus'] == 'X Cookie：已配置 · 待验证'
    page.requestParse()
    assert page.state['cookieAuthStatus'] == 'X Cookie：正在验证…'


@pytest.mark.parametrize('domain', ['youtube.com', 'douyin.com', 'example.org'])
@pytest.mark.parametrize(('cookies', 'expected'), [
    ((), AuthState.INVALID),
    ((cookie('.unrelated.org'),), AuthState.INVALID),
    ((cookie('.{domain}', expires=1),), AuthState.INVALID),
    ((cookie('.{domain}'),), AuthState.UNKNOWN),
    ((cookie('.{domain}', expires=1), cookie('.{domain}')), AuthState.UNKNOWN),
])
def test_generic_local_evidence_is_conservative(domain, cookies, expected):
    cookies = tuple(replace_cookie_domain(c, domain) for c in cookies)
    assert detect_auth_state(SimpleNamespace(cookiejar=jar(*cookies)), 'https://' + domain + '/video',
                             'Generic', cookie_enabled=True, cookie_profile=profile(domain)) is expected


def replace_cookie_domain(item, domain):
    import copy
    result = copy.copy(item)
    result.domain = item.domain.replace('{domain}', domain)
    return result


@pytest.mark.parametrize('alias', ['x.com', 'twitter.com', 't.co'])
@pytest.mark.parametrize(('token', 'expected'), [
    (None, AuthState.INVALID),
    (cookie('.x.com', 'auth_token', expires=1), AuthState.INVALID),
    (cookie('.twitter.com', 'auth_token'), AuthState.UNKNOWN),
])
def test_x_aliases_and_key_cookie_expiration(alias, token, expected):
    cookies = (cookie('.x.com', 'ct0'),) + ((token,) if token else ())
    assert detect_auth_state(SimpleNamespace(cookiejar=jar(*cookies)), f'https://{alias}/post/1', 'Twitter',
                             cookie_enabled=True, cookie_profile=profile('x.com')) is expected


@pytest.mark.parametrize(('success', 'evidence', 'expected'), [
    (True, {'x.com'}, AuthState.VALID),
    (False, {'x.com'}, AuthState.UNKNOWN),
    (True, set(), AuthState.UNKNOWN),
])
def test_x_valid_requires_authenticated_native_extraction(success, evidence, expected):
    ydl = SimpleNamespace(cookiejar=jar(cookie('.x.com', 'auth_token')), cookie_auth_evidence=evidence)
    assert detect_auth_state(ydl, 'https://x.com/post/1', 'Twitter', cookie_enabled=True,
                             cookie_profile=profile('x.com'), extraction_succeeded=success) is expected


@pytest.mark.parametrize('matched', [True, False])
@pytest.mark.parametrize(('state', 'expected'), [
    (AuthState.INVALID, 'COOKIE_INVALID'),
    (AuthState.UNKNOWN, 'TEMPORARY_EXTRACTOR_ERROR'),
    (AuthState.VALID, 'NO_VIDEO'),
])
def test_x_no_video_error_needs_independent_auth_evidence(state, expected, matched):
    from yt_downloader.services.media_errors import classify_auth_metadata_error
    code, _, _ = classify_auth_metadata_error(DownloadError('No video could be found in this tweet'),
        auth_state=state, cookie_matched=matched, site='X')
    assert code == ('TEMPORARY_EXTRACTOR_ERROR' if state is AuthState.INVALID and not matched else expected)


@pytest.mark.parametrize('matched', [True, False])
def test_youtube_fresh_cookies_evidence_preserved_through_exception_chain(matched):
    from yt_downloader.services.media_errors import classify_auth_metadata_error
    nested = DownloadError('Fresh cookies are needed; use --cookies-from-browser')
    outer = DownloadError('Extraction failed', exc_info=(type(nested), nested, None))
    code, _, state = classify_auth_metadata_error(outer, auth_state=AuthState.UNKNOWN,
                                                 cookie_matched=matched, site='YouTube')
    assert code == ('COOKIE_INVALID' if matched else 'COOKIE_REQUIRED')
    assert state is (AuthState.INVALID if matched else AuthState.UNKNOWN)


@pytest.mark.parametrize(('message', 'expected'), [
    ('Sign in to confirm your age', 'AUTH_REQUIRED'),
    ('Login required', 'AUTH_REQUIRED'),
    ('Use --cookies-from-browser', 'COOKIE_REQUIRED'),
    ('Private video', 'PRIVATE_MEDIA'),
    ('Connection timed out', 'NETWORK_ERROR'),
])
def test_permissions_and_network_errors_do_not_prove_cookie_expiration(message, expected):
    from yt_downloader.services.media_errors import classify_auth_metadata_error
    code, _, state = classify_auth_metadata_error(Exception(message), auth_state=AuthState.UNKNOWN,
                                                 cookie_matched=True, site='YouTube')
    assert code == expected
    assert state is AuthState.UNKNOWN


def test_source_read_error_is_unknown_not_expired():
    class Unreadable:
        @property
        def cookiejar(self): raise OSError('Source not readable')
    assert detect_auth_state(Unreadable(), 'https://x.com/post/1', 'Twitter', cookie_enabled=True,
                             cookie_profile=profile('x.com')) is AuthState.UNKNOWN


def test_bilibili_malformed_nav_is_unknown():
    from io import BytesIO
    ydl = SimpleNamespace(cookiejar=jar(), urlopen=lambda _: BytesIO(b'{"code":0,"data":[1]}'))
    assert detect_auth_state(ydl, 'https://www.bilibili.com/bangumi/play/ss46089', 'BiliBiliBangumiSeason',
                             cookie_enabled=True, cookie_profile=profile('bilibili.com')) is AuthState.UNKNOWN


def test_native_x_auth_observer_does_not_read_body_or_keep_guest_evidence(monkeypatch):
    import yt_dlp
    from yt_dlp.networking.common import Request
    from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL
    class Response:
        status = 200
        def read(self): raise AssertionError('Observer cannot read a response body')
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'urlopen', lambda *_: Response())
    with ReadOnlyCookieYoutubeDL({'quiet': True, 'cachedir': False}) as ydl:
        ydl.cookiejar.set_cookie(cookie('.x.com', 'auth_token'))
        ydl.urlopen(Request('https://api.x.com/1.1/test', headers={'x-twitter-auth-type': 'OAuth2Session'}))
        assert ydl.cookie_auth_evidence == {'x.com'}
        assert ydl.cookie_used_sites == {'x.com'}
        ydl.urlopen(Request('https://cdn.syndication.twimg.com/tweet-result'))
        assert ydl.cookie_auth_evidence == set()
        ydl.urlopen(Request('https://api.x.com/1.1/test'))
        assert ydl.cookie_auth_evidence == set()


@pytest.mark.parametrize('state', [AuthState.VALID, AuthState.INVALID, AuthState.UNKNOWN])
def test_auth_failure_survives_worker_serialization_and_updates_ui(qapp, state):
    from yt_downloader.core.errors import ErrorContext
    from yt_downloader.app import AppController
    from yt_downloader.workers.metadata_process import _serialize_error, _deserialize_error
    from yt_downloader.ui.quick_download import DownloadPresenter
    page = DownloadPresenter('', None)
    page.set_cookie_state((profile('x.com'),))
    page.set_url('https://x.com/post/1')
    page.setCookieEnabled(True)
    page.requestParse()
    error = AppError('COOKIE_INVALID' if state is AuthState.INVALID else 'TEMPORARY_EXTRACTOR_ERROR',
                     'Synthetic failure', 'No video', ErrorContext(auth_state=state, cookie_used=True, cookie_site='X'))
    decoded = _deserialize_error(_serialize_error(error))
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(update=lambda **_: None))
    captured = []
    controller.show_error = captured.append
    controller._apply_metadata_error(decoded)
    assert captured == [decoded]
    assert page.state['cookieAuthStatus'].startswith('X Cookie：')
    assert '正在验证' not in page.state['cookieAuthStatus']
    assert page.state['cookieAuthInvalid'] is (state is AuthState.INVALID)


def test_auth_site_profile_and_cookie_toggle_reset_status(qapp):
    from yt_downloader.ui.quick_download import DownloadPresenter
    page = DownloadPresenter('', None)
    page.set_cookie_state((profile('x.com'), profile('bilibili.com'), profile('douyin.com')))
    page.setCookieEnabled(True)
    page.set_url('https://b23.tv/test')
    page._show_auth_state(AuthState.VALID, cookie_used=True)
    assert page.state['cookieAuthStatus'] == 'B站 Cookie：登录有效'
    page.set_url('https://twitter.com/post/1')
    assert page.state['cookieAuthStatus'] == 'X Cookie：已配置 · 待验证'
    page.set_cookie_parse_error('COOKIE_INVALID', auth_state=AuthState.INVALID)
    assert page.state['cookieAuthStatus'] == 'X Cookie：登录失效'
    page.set_cookie_state((replace(profile('x.com'), browser_profile='Replacement'),))
    assert page.state['cookieAuthStatus'] == 'X Cookie：已配置 · 待验证'
    page.set_url('https://v.douyin.com/test')
    assert page.state['cookieAuthStatus'] == '抖音 Cookie：未配置'
    page.setCookieEnabled(False)
    assert page.state['cookieAuthStatus'] == ''


def test_all_auth_copy_is_complete_and_switches_live(qapp):
    from yt_downloader.ui.localization import Translator
    from yt_downloader.ui.quick_download import DownloadPresenter
    from yt_downloader.core.models import SUPPORTED_LOCALES
    from yt_downloader.services.error_actions import ERROR_PRESENTATION
    translator = Translator('zh-CN')
    page = DownloadPresenter('', None, translator=translator)
    page.set_cookie_state((profile('bilibili.com'),))
    page.set_url('https://www.bilibili.com/video/test')
    page.setCookieEnabled(True)
    page._show_auth_state(AuthState.INVALID)
    for locale in SUPPORTED_LOCALES:
        translator.setLanguage(locale)
        assert translator.validateCoverage() == []
        assert page.state['cookieAuthStatus'] == translator.text('download.cookie_invalid',
                {'site': translator.text('cookie.site_bilibili')})
        for key in (*ERROR_PRESENTATION['COOKIE_INVALID'][:2], *ERROR_PRESENTATION['NO_VIDEO'][:2]):
            assert '[missing:' not in translator.text(key, {'site': 'X'})


def test_x_secret_names_redacted_from_error_worker_and_logger():
    import json
    from yt_downloader.core.errors import ErrorContext
    from yt_downloader.services.error_report_service import build_error_report, redact_sensitive
    from yt_downloader.services.media_resolver import _YdlLogger
    from yt_downloader.workers.metadata_process import _serialize_error
    secret = 'synthetic-never-record-this'
    raw = f'auth_token={secret}; ct0={secret}\nCookie: session={secret}\n' + json.dumps({'auth_token': secret, 'ct0': secret})
    log = _YdlLogger()
    log.error(raw)
    error = AppError('COOKIE_INVALID', raw, raw, ErrorContext(traceback_text=raw, log_excerpt=raw,
                     auth_state=AuthState.INVALID, cookie_used=True, cookie_site='X'))
    assert secret not in redact_sensitive(raw)
    assert secret not in json.dumps(_serialize_error(error))
    assert secret not in '\n'.join(log.lines)
    assert secret not in build_error_report(error, app_version='test')


@pytest.mark.parametrize('change', ['url', 'profile', 'off'])
def test_auth_context_change_cancels_old_metadata_before_it_can_overwrite_state(qapp, change):
    from yt_downloader.core.models import ParseState
    from yt_downloader.ui.quick_download import DownloadPresenter
    page = DownloadPresenter('', None)
    page.set_cookie_state((profile('x.com'),))
    page.set_url('https://x.com/post/1')
    page.setCookieEnabled(True)
    page.requestParse()
    page.set_parse_state(ParseState.RUNNING)
    cancelled = []
    page.parse_cancel_requested.connect(lambda: cancelled.append(True))
    if change == 'url': page.set_url('https://youtube.com/watch?v=test')
    elif change == 'profile': page.set_cookie_state((replace(profile('x.com'), browser_profile='New'),))
    else: page.setCookieEnabled(False)
    assert cancelled == [True]
    assert page.parse_state is ParseState.CANCELLING
    assert '正在验证' not in page.state['cookieAuthStatus']


@pytest.mark.parametrize('expires', [1, 2147483647])
def test_real_cookie_file_local_validation_is_read_only(tmp_path, expires):
    from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL, cookie_options
    path = tmp_path / 'source.txt'
    path.write_text('# Netscape HTTP Cookie File\n.x.com\tTRUE\t/\tTRUE\t'
                    + str(expires) + '\tauth_token\tsynthetic-test-only\n', encoding='utf-8')
    original = path.read_bytes()
    source = CookieProfile('test', 'X', 'file', cookie_file=str(path), domain_hint='x.com')
    with ReadOnlyCookieYoutubeDL(dict(cookie_options(source), quiet=True, cachedir=False)) as ydl:
        assert detect_auth_state(ydl, 'https://x.com/post/1', 'Twitter', cookie_enabled=True,
                                 cookie_profile=source) is (AuthState.INVALID if expires == 1 else AuthState.UNKNOWN)
    assert path.read_bytes() == original


def test_invalid_cookie_dialog_body_and_actions_match_page(quick_window, qapp):
    from yt_downloader.core.errors import ErrorContext
    from yt_downloader.services.error_actions import error_presentation
    from conftest import run_frames
    page = quick_window.download_page
    page.set_cookie_state((profile('x.com'),))
    page.set_url('https://x.com/post/1')
    page.setCookieEnabled(True)
    page.set_cookie_parse_error('COOKIE_INVALID', auth_state=AuthState.INVALID, cookie_used=True)
    title, body, actions = error_presentation('COOKIE_INVALID')
    error = AppError('COOKIE_INVALID', 'Ignored generic text', 'Sanitized technical details',
                     ErrorContext(auth_state=AuthState.INVALID, cookie_used=True, cookie_site='X'),
                     title_message_id=title, body_message_id=body)
    from yt_downloader.ui.quick_dialogs import ErrorSession
    session = ErrorSession(error, 'Safe report', quick_window, actions=actions,
                           action_callbacks={action: lambda: None for action in actions})
    session.show()
    run_frames(qapp)
    assert page.state['cookieAuthStatus'] == 'X Cookie：登录失效'
    assert 'X' in session.state['message'] and '失效' in session.state['message']
    assert [a['id'] for a in session.state['errorActions']] == ['OPEN_COOKIE_MANAGER', 'REPARSE']
    quick_window.i18n.setLanguage('en-US')
    assert page.state['cookieAuthStatus'] == 'X cookies: session expired'
    assert 'X' in session.state['message']
    assert session.state['errorActions'][0]['label'] == 'Manage cookies'
    session.reject()


def test_extractor_guest_cookies_cannot_validate_an_empty_saved_source():
    from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL
    class GuestYDL(ReadOnlyCookieYoutubeDL):
        def extract_info(self, *_args, **_kwargs):
            self.cookiejar.set_cookie(cookie('.example.org', 'visitor'))
            return {'id': 'test', 'title': 'Public video', 'extractor_key': 'Generic',
                    'formats': [{'format_id': '1', 'width': 1280, 'height': 720,
                                 'vcodec': 'avc1', 'acodec': 'aac', 'ext': 'mp4'}]}
    # Load a real in-memory jar without a browser source; the selected reference
    # is retained by the resolver, while the test factory deliberately loads none.
    def factory(options):
        return GuestYDL({k: v for k, v in options.items() if k != 'cookiesfrombrowser'})
    media = MediaResolver(ydl_factory=factory, cookie_enabled=True,
                          cookie_profile=profile('example.org')).fetch_metadata(
                          'https://example.org/video', include_thumbnail=False)
    assert media.auth_state is AuthState.INVALID
    assert not media.cookie_used


def test_cookie_invalid_message_translates_in_settings_feedback(quick_window, qapp):
    from yt_downloader.services.media_errors import classify_auth_metadata_error
    from conftest import find_item, run_frames
    from yt_downloader.core.models import SUPPORTED_LOCALES
    code, message, _ = classify_auth_metadata_error(
        DownloadError('No video could be found in this tweet'), auth_state=AuthState.INVALID,
        cookie_matched=True, site='X')
    assert code == 'COOKIE_INVALID'
    quick_window.cookies.update(authRequired=True, message=message)
    quick_window.openCookieSettings()
    for locale in SUPPORTED_LOCALES:
        quick_window.i18n.setLanguage(locale)
        run_frames(qapp, 70)
        feedback = find_item(quick_window, 'cookieFeedback')
        assert feedback.isVisible()
        assert feedback.property('text') == quick_window.i18n.text('error.cookie_invalid.body', {'site': 'X'})

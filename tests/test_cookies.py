from pathlib import Path
import pytest


def test_cookie_profiles_build_explicit_options_without_secrets(tmp_path):
    from yt_downloader.services.cookie_service import CookieProfile, cookie_options
    assert cookie_options(None) == {}
    profile = CookieProfile('youtube', 'YouTube / Firefox', 'browser', browser='firefox', domain_hint='youtube.com')
    assert cookie_options(profile) == {'cookiesfrombrowser': ('firefox',)}
    path = tmp_path / 'cookies.txt'
    path.write_text('# Netscape HTTP Cookie File\n.example.org\tTRUE\t/\tFALSE\t0\tSID\tfixture\n', encoding='utf-8')
    original = path.read_bytes()
    assert cookie_options(CookieProfile('file', 'File', 'file', cookie_file=str(path))) == {'cookiefile': str(path)}
    assert path.read_bytes() == original


@pytest.mark.parametrize('text', [
    'SAPISID=TEST_COOKIE_SECRET_123; HSID=TEST_COOKIE_SECRET_123',
    'session=TEST_COOKIE_SECRET_123',
    'Cookie: SID=TEST_COOKIE_SECRET_123',
    'Request headers: Cookie: arbitrary=TEST_COOKIE_SECRET_123',
    'Authorization: Bearer TEST_BEARER_SECRET_456',
    r'Could not copy browser profile C:\Users\FixtureUser\AppData\Local\Chrome\User Data\Default',
])
def test_cookie_diagnostics_redact_secrets_and_browser_user_paths(text):
    from yt_downloader.services.error_report_service import redact_sensitive
    result = redact_sensitive(text)
    assert 'TEST_COOKIE_SECRET_123' not in result
    assert 'TEST_BEARER_SECRET_456' not in result
    assert 'FixtureUser' not in result


def test_cookie_store_persists_references_and_recommends_exact_domain(tmp_path):
    from yt_downloader.services.cookie_service import CookieProfile, CookieProfileStore, recommended_profile
    profile = CookieProfile('one', 'Example', 'browser', browser='firefox', domain_hint='example.org')
    store = CookieProfileStore(tmp_path / 'profiles.json')
    store.save((profile,))
    assert store.load() == (profile,)
    assert recommended_profile(store.load(), 'https://www.example.org/a') == profile
    assert recommended_profile(store.load(), 'https://example.org.evil.test') is None


def test_site_cookie_routing_handles_aliases_and_conflicts_without_cross_site_leak():
    from yt_downloader.services.cookie_service import route_cookie_profile, CookieProfile
    x = CookieProfile('x', 'X', 'browser', browser='firefox', domain_hint='twitter.com')
    bili = CookieProfile('b', 'Bili', 'browser', browser='firefox', domain_hint='bilibili.com')
    profiles = (x, bili)
    assert route_cookie_profile(profiles, 'https://x.com/post/1').profile == x
    assert route_cookie_profile(profiles, 'https://b23.tv/a').profile == bili
    assert route_cookie_profile(profiles, 'https://x.com.evil.example/a').profile is None
    assert route_cookie_profile(profiles, 'https://vimeo.com/a').status == 'missing'
    duplicate = CookieProfile('x2', 'Other X', 'browser', browser='edge', domain_hint='x.com')
    assert route_cookie_profile((*profiles, duplicate), 'https://x.com/post/1').status == 'conflict'


def test_cookie_file_is_never_written_by_yt_dlp(tmp_path):
    from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL
    path = tmp_path / 'cookies.txt'
    content = '# Netscape HTTP Cookie File\n.example.org\tTRUE\t/\tFALSE\t0\tSID\tfixture\n'
    path.write_text(content, encoding='utf-8')
    before = path.stat().st_mtime_ns
    with ReadOnlyCookieYoutubeDL({'cookiefile': str(path), 'quiet': True}) as ydl:
        assert len(list(ydl.cookiejar)) == 1
    assert path.read_text(encoding='utf-8') == content
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize('message,code', [('Could not copy Chrome cookie database', 'BROWSER_PROFILE_LOCKED'),
                                       ('Failed to decrypt with DPAPI', 'COOKIE_DECRYPT_FAILED'),
                                       ('could not find firefox cookies database', 'BROWSER_COOKIE_READ_FAILED')])
def test_browser_cookie_errors_have_actionable_categories(message, code):
    from yt_downloader.services.media_errors import classify_metadata_error
    assert classify_metadata_error(Exception(message))[0] == code


@pytest.mark.parametrize('content', ['not cookies', '# Netscape HTTP Cookie File\ninvalid\tline', '# Netscape HTTP Cookie File\n.example\tTRUE\t/\tFALSE\tnot-time\tSID\tfixture'])
def test_invalid_cookie_files_fail_without_echoing_contents(tmp_path, content):
    from yt_downloader.services.cookie_service import CookieProfile, cookie_options
    path = tmp_path / 'cookies.txt'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError) as caught:
        cookie_options(CookieProfile('one', 'File', 'file', cookie_file=str(path)))
    assert content not in str(caught.value)


def test_missing_cookie_file_is_actionable(tmp_path):
    from yt_downloader.services.cookie_service import CookieProfile, cookie_options
    with pytest.raises(ValueError, match='不存在'):
        cookie_options(CookieProfile('one', 'File', 'file', cookie_file=str(tmp_path / 'missing.txt')))


def test_cookie_secrets_never_reach_log_or_copy_report(tmp_path):
    import logging
    from yt_downloader.infrastructure.logging_config import RedactingFormatter
    from yt_downloader.services.error_report_service import build_error_report
    from yt_downloader.core.errors import AppError
    secret = 'Cookie: SID=TEST_COOKIE_SECRET_123\nAuthorization: Bearer TEST_BEARER_SECRET_456'
    record = logging.LogRecord('fixture', logging.ERROR, '', 0, secret, (), None)
    log = RedactingFormatter('%(message)s').format(record)
    report = build_error_report(AppError('cookie', '读取失败', secret), app_version='test')
    assert 'TEST_COOKIE_SECRET_123' not in log + report
    assert 'TEST_BEARER_SECRET_456' not in log + report


def test_reference_cookie_file_reaches_only_selected_http_domain(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL, cookie_options, CookieProfile
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get('Cookie', ''))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
        def log_message(self, *args):
            pass
    path = tmp_path / 'cookies.txt'
    path.write_text('# Netscape HTTP Cookie File\n127.0.0.1\tFALSE\t/\tFALSE\t2147483647\tSID\tfixture\n', encoding='utf-8')
    original = path.read_bytes()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        options = cookie_options(CookieProfile('test', 'Fixture', 'file', cookie_file=str(path)))
        with ReadOnlyCookieYoutubeDL(dict(options, proxy='', quiet=True)) as ydl:
            with ydl.urlopen(f'http://127.0.0.1:{server.server_port}/') as response:
                assert response.read() == b'ok'
        assert seen == ['SID=fixture']
        assert path.read_bytes() == original
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

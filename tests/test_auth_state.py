from io import BytesIO
import json
from contextlib import AbstractContextManager

import pytest

from yt_downloader.core.models import AuthState, CookieProfile
from yt_downloader.services.auth_state import detect_auth_state
from yt_downloader.services.media_resolver import MediaResolver


PROFILE = CookieProfile('bili', 'B站', 'browser', browser='firefox', domain_hint='bilibili.com')
URL = 'https://www.bilibili.com/video/BV1G4hD61EqA/'


class FakeYDL:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def urlopen(self, request):
        if self.error:
            raise self.error
        return BytesIO(json.dumps(self.payload).encode())


@pytest.mark.parametrize(('is_login', 'expected'), [
    (True, AuthState.VALID),
    (False, AuthState.INVALID),
])
def test_bilibili_auth_state_uses_explicit_nav_is_login(is_login, expected):
    ydl = FakeYDL({'code': 0, 'data': {'isLogin': is_login}})

    assert detect_auth_state(ydl, URL, 'BiliBili', cookie_enabled=True, cookie_profile=PROFILE) is expected


@pytest.mark.parametrize('ydl', [
    FakeYDL(error=OSError('network unavailable')),
    FakeYDL({'code': -1, 'data': {'isLogin': False}}),
    FakeYDL({'code': 0, 'data': {}}),
])
def test_bilibili_auth_state_is_unknown_without_explicit_success_or_failure(ydl):
    assert detect_auth_state(ydl, URL, 'BiliBili', cookie_enabled=True, cookie_profile=PROFILE) is AuthState.UNKNOWN


def test_auth_state_is_not_applicable_when_cookie_is_off_or_media_is_not_bilibili():
    ydl = FakeYDL(error=AssertionError('auth endpoint must not be requested'))

    assert detect_auth_state(ydl, URL, 'BiliBili', cookie_enabled=False, cookie_profile=PROFILE) is AuthState.NOT_APPLICABLE
    assert detect_auth_state(ydl, 'https://example.org/video', 'Generic',
                             cookie_enabled=True, cookie_profile=PROFILE) is AuthState.NOT_APPLICABLE


def test_auth_state_is_unknown_when_cookie_is_enabled_without_a_routed_profile():
    ydl = FakeYDL({'code': 0, 'data': {'isLogin': False}})

    assert detect_auth_state(ydl, URL, 'BiliBili', cookie_enabled=True, cookie_profile=None) is AuthState.UNKNOWN


def test_media_resolver_attaches_cookie_auth_state_without_blocking_metadata():
    info = {'id': 'fixture', 'title': 'fixture', 'extractor_key': 'BiliBili',
            'formats': [{'format_id': 'video', 'ext': 'mp4', 'width': 1920,
                         'height': 1080, 'fps': 30, 'vcodec': 'avc1', 'acodec': 'mp4a'}]}

    class ResolverYDL(AbstractContextManager):
        def __init__(self, _options):
            pass
        def __exit__(self, *_args):
            return None
        def extract_info(self, _url, *, download):
            assert download is False
            return info
        def sanitize_info(self, data):
            return data
        def urlopen(self, _request):
            return BytesIO(b'{"code":0,"data":{"isLogin":true}}')

    media = MediaResolver(ydl_factory=ResolverYDL, require_deno=False,
                          cookie_profile=PROFILE, cookie_enabled=True).fetch_metadata(
                              URL, include_thumbnail=False)

    assert media.auth_state is AuthState.VALID
    assert [option.label for option in media.formats] == ['1080p']

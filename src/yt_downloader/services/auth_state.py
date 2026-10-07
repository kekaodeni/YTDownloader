"""Explicit authentication checks for supported providers."""

from __future__ import annotations

import json

from yt_dlp.networking.common import Request

from yt_downloader.core.models import AuthState
from yt_downloader.services.cookie_service import cookie_site_domain, route_cookie_profile, _site_host


_BILIBILI_NAV_URL = 'https://api.bilibili.com/x/web-interface/nav'


def _generic_source_state(cookies) -> AuthState:
    if cookies is None:
        return AuthState.UNKNOWN
    if not cookies or all(getattr(c, 'is_expired', lambda: False)() for c in cookies):
        return AuthState.INVALID
    return AuthState.UNKNOWN


def _bilibili_validator(ydl, cookies, *, extraction_succeeded=False, validate_session=True,
                        source_auth_state=None) -> AuthState:
    if not validate_session:
        return _generic_source_state(cookies)
    response = None
    try:
        response = ydl.urlopen(Request(_BILIBILI_NAV_URL, extensions={'timeout': 5.0}))
        payload = json.loads(response.read())
    except Exception:
        return AuthState.UNKNOWN
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
    if not isinstance(payload, dict) or payload.get('code') != 0:
        return AuthState.UNKNOWN
    data = payload.get('data')
    is_login = data.get('isLogin') if isinstance(data, dict) else None
    if is_login is True:
        return AuthState.VALID
    if is_login is False:
        return AuthState.INVALID
    return AuthState.UNKNOWN


def _x_validator(ydl, cookies, *, extraction_succeeded=False, validate_session=True,
                 source_auth_state=None) -> AuthState:
    if source_auth_state is AuthState.INVALID:
        return AuthState.INVALID
    if cookies is None:
        return AuthState.UNKNOWN
    login = [c for c in cookies if getattr(c, 'name', '') == 'auth_token' and c.value]
    if not login or all(c.is_expired() for c in login):
        return AuthState.INVALID
    if validate_session and extraction_succeeded and 'x.com' in getattr(ydl, 'cookie_auth_evidence', ()):
        return AuthState.VALID
    return AuthState.UNKNOWN


VALIDATOR_REGISTRY = {'bilibili.com': _bilibili_validator, 'x.com': _x_validator}


def matching_cookies(ydl, url):
    """Inspect names/domains/expiry in memory only; never copy credential values."""
    cookiejar = getattr(ydl, 'cookiejar', None)
    host = cookie_site_domain(url)
    try:
        return [c for c in cookiejar
                if host == _site_host(c.domain.lstrip('.')) or host.endswith('.' + c.domain.lstrip('.'))]
    except TypeError:
        getter = getattr(cookiejar, 'get_cookies_for_url', None)
        return list(getter(url)) if callable(getter) else None


def detect_auth_state(ydl, url: str, extractor_key: str, *, cookie_enabled: bool, cookie_profile,
                      extraction_succeeded=False, validate_session=True,
                      source_auth_state: AuthState | None = None) -> AuthState:
    """Generic local evidence first, optional provider confirmation second."""
    if not cookie_enabled or cookie_profile is None or cookie_profile.source_type == 'none':
        return AuthState.NOT_APPLICABLE
    if route_cookie_profile((cookie_profile,), url).profile is None:
        return AuthState.NOT_APPLICABLE
    try:
        cookies = matching_cookies(ydl, url)
    except Exception:
        return AuthState.UNKNOWN
    validator = VALIDATOR_REGISTRY.get(cookie_site_domain(url))
    if validator:
        try:
            return validator(ydl, cookies, extraction_succeeded=extraction_succeeded,
                             validate_session=validate_session, source_auth_state=source_auth_state)
        except Exception:
            return AuthState.UNKNOWN
    if source_auth_state is not None:
        # Native extraction may add anonymous visitor cookies. They are not
        # evidence about the user's selected Cookie source.
        return source_auth_state
    return _generic_source_state(cookies)

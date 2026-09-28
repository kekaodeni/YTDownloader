"""Explicit authentication checks for supported providers."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from yt_dlp.networking.common import Request

from yt_downloader.core.models import AuthState


_BILIBILI_NAV_URL = 'https://api.bilibili.com/x/web-interface/nav'


def _is_bilibili(url: str, extractor_key: str) -> bool:
    host = (urlsplit(url).hostname or '').casefold().removeprefix('www.')
    return extractor_key.casefold() in {'bilibili', 'bilibiliuser', 'bilibiliwatchlater'} or (
        host == 'bilibili.com' or host.endswith('.bilibili.com') or host == 'b23.tv')


def detect_auth_state(ydl, url: str, extractor_key: str, *, cookie_enabled: bool, cookie_profile) -> AuthState:
    """Use Bilibili's explicit nav isLogin field; format availability is not auth evidence."""
    if not cookie_enabled:
        return AuthState.NOT_APPLICABLE
    if not _is_bilibili(url, extractor_key):
        return AuthState.NOT_APPLICABLE
    if cookie_profile is None:
        return AuthState.UNKNOWN
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
    is_login = (payload.get('data') or {}).get('isLogin')
    if is_login is True:
        return AuthState.VALID
    if is_login is False:
        return AuthState.INVALID
    return AuthState.UNKNOWN

"""Generic HTTP(S) input validation plus legacy YouTube canonicalization."""

from __future__ import annotations

import re
import ipaddress
from urllib.parse import parse_qs, urlparse


class InvalidMediaUrl(ValueError):
    """Input is unsafe or is not an absolute HTTP(S) URL."""


def normalize_media_url(raw_url: str) -> str:
    text = raw_url.strip()
    try:
        if not text or re.search(r'[\s\x00-\x1f\x7f\\<>]', text):
            raise ValueError('Invalid URL characters')
        parsed = urlparse(text)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError('Expected HTTP(S) URL without credentials')
        host = parsed.hostname.encode('idna').decode('ascii')
        if ':' in host:
            ipaddress.IPv6Address(host)
        elif len(host) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.rstrip('.').split('.')):
            raise ValueError('Invalid hostname')
        if parsed.netloc.endswith(':') or (parsed.port is not None and parsed.port == 0):
            raise ValueError('Invalid port')
    except (ValueError, UnicodeError) as exc:
        raise InvalidMediaUrl('请输入有效的 HTTP 或 HTTPS 链接，不要包含账号、密码或控制字符。') from exc
    # Preserve meaningful query parameters and fragments for the extractor.
    return text


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}


class InvalidYoutubeUrl(ValueError):
    """Raised when input is not a supported single-video YouTube URL."""


def extract_video_id(raw_url: str) -> str:
    text = raw_url.strip()
    if not text:
        raise InvalidYoutubeUrl("请输入 YouTube 视频链接。")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _ALLOWED_HOSTS:
        raise InvalidYoutubeUrl("仅支持 YouTube 单视频链接。")

    host = parsed.hostname or ""
    parts = [part for part in parsed.path.split("/") if part]
    candidate = ""
    if host.endswith("youtu.be"):
        candidate = parts[0] if parts else ""
    elif parsed.path.rstrip("/") == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
        candidate = parts[1]

    if not _VIDEO_ID.fullmatch(candidate):
        raise InvalidYoutubeUrl("该链接不是受支持的 YouTube 单视频地址。")
    return candidate


def normalize_youtube_url(raw_url: str) -> str:
    """Return a privacy-reduced canonical URL containing only the video id."""
    return f"https://www.youtube.com/watch?v={extract_video_id(raw_url)}"

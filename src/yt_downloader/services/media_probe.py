"""Eligibility and bounded session cache for optional media metadata probing."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


_SEMANTIC_LABEL = re.compile(r"(?:\b\d{3,4}\s*p\b|\b4k\b|\b8k\b|hdr|dolby|杜比|高码率|60\s*fps)", re.I)


def _has_semantic_quality(item: Mapping[str, Any]) -> bool:
    """Return true only when yt-dlp supplied a recognizable user-facing tier."""
    for key in ("quality", "qn", "site_quality", "quality_label", "quality_rank",
                "dynamic_range", "format_note", "format", "resolution"):
        value = item.get(key)
        if value is None:
            continue
        if key == "dynamic_range" and str(value).strip():
            return True
        # Bilibili's numeric qn tiers carry meaning even without a text label.
        if isinstance(value, (int, float)) and int(value) in {
            6, 16, 32, 64, 74, 80, 112, 116, 120, 125, 126,
            144, 240, 360, 480, 540, 720, 1080, 1440, 2160, 4320,
        }:
            return True
        if isinstance(value, str) and _SEMANTIC_LABEL.search(value):
            return True
    return any(isinstance(item.get(key), str) and _SEMANTIC_LABEL.search(item[key])
               for key in ("format_note", "format", "resolution"))


def needs_media_probe(media_format: Mapping[str, Any]) -> bool:
    """Whether an already-resolved yt-dlp video format needs display metadata.

    This deliberately rejects webpage URLs and deferred entries: ffprobe is only
    permitted to inspect the actual stream URL yt-dlp returned.
    """
    if not isinstance(media_format, Mapping):
        return False
    if media_format.get("vcodec") == "none" or media_format.get("has_drm"):
        return False
    if media_format.get("width") and media_format.get("height"):
        return False
    if _has_semantic_quality(media_format):
        return False
    url = media_format.get("url")
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlsplit(url)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return False
    except ValueError:
        return False
    protocol = str(media_format.get("protocol") or "").casefold()
    path = parsed.path.casefold()
    ext = str(media_format.get("ext") or "").casefold()
    return (protocol.startswith(("m3u8", "http_dash_segments", "dash"))
            or ext in {"mp4", "m4v", "webm", "mov", "ts", "m4s", "mkv", "flv"}
            or path.endswith((".m3u8", ".mpd", ".mp4", ".m4v", ".webm", ".mov", ".ts", ".m4s", ".mkv", ".flv")))


def probe_cache_key(media_format: Mapping[str, Any]) -> str:
    """Opaque identity; signed URLs are never exposed as cache keys/log text."""
    identity = "\0".join((str(media_format.get("url") or ""),
                          str(media_format.get("format_id") or ""),
                          str(media_format.get("protocol") or "")))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()

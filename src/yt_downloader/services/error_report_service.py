"""Error classification helpers and privacy-preserving copy reports."""

from __future__ import annotations

from datetime import datetime
import platform
import re
import sys
from typing import Final

from yt_downloader.core.errors import AppError


_SECRET_NAMES: Final[str] = r"api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|authorization|cookie|signature|sig|credential"
_URL_AUTH_RE = re.compile(r'(?i)(https?://)[^/@\s]+@')
_HEADER_RE = re.compile(r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:\s*).*$")
_JSON_RE = re.compile(rf"(?i)([\"'](?:{_SECRET_NAMES})[\"']\s*:\s*)[\"'][^\"']*[\"']")
_KV_RE = re.compile(rf"(?i)\b({_SECRET_NAMES})(\s*=\s*)([^&\s,;]+)")
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+")


def redact_sensitive(text: str | None) -> str:
    if not text:
        return ""
    value = str(text)
    value = _URL_AUTH_RE.sub(r'\1[REDACTED]@', value)
    value = _HEADER_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    value = _JSON_RE.sub(lambda match: f'{match.group(1)}"[REDACTED]"', value)
    value = _KV_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    value = _BEARER_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    return value


def _safe_url(url: str) -> str:
    return redact_sensitive(url)


def build_error_report(
    error: AppError,
    *,
    app_version: str,
    python_version: str | None = None,
    os_version: str | None = None,
    yt_dlp_version: str = "Unknown",
    ffmpeg_version: str = "Unknown",
    timestamp: str | None = None,
) -> str:
    context = error.context
    values = {
        "Application Version": app_version,
        "Time": timestamp or datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "Windows Version": os_version or platform.platform(),
        "Python Version": python_version or sys.version.split()[0],
        "yt-dlp Version": yt_dlp_version,
        "FFmpeg Version": ffmpeg_version,
        "Video URL": _safe_url(context.url),
        "Current Stage": context.stage or "Unknown",
        "Selected Format": context.selected_format or "Unknown",
        "Output Directory": context.output_directory or "Unknown",
        "Error Code": error.code,
        "Exception Type": type(error).__name__,
        "Exception Message": error.technical_message,
        "Traceback": context.traceback_text or "Unavailable",
        "Relevant Log": context.log_excerpt or "Unavailable",
    }
    lines = ["--------------------------------", "YT Downloader Error Report", "--------------------------------", ""]
    for label, value in values.items():
        lines.extend((f"{label}:", redact_sensitive(str(value)), ""))
    lines.append("--------------------------------")
    return "\n".join(lines)

"""Metadata retrieval through yt-dlp's supported Python API."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
import logging
from pathlib import Path
import threading
import traceback
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

import requests
import yt_dlp
from yt_dlp.utils import DownloadError

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.services.media_metadata import resolve_metadata
from yt_downloader.services.media_errors import classify_metadata_error
from yt_downloader.core.models import ResolvedMedia
from yt_downloader.services.auth_state import detect_auth_state
from yt_downloader.core.url import InvalidMediaUrl, normalize_media_url
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.network_policy import NetworkPolicy
from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL, cookie_options
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.media_probe import needs_media_probe, probe_cache_key
from yt_downloader.services.metadata_language import youtube_metadata_options


logger = logging.getLogger(__name__)


class _Response(Protocol):
    content: bytes

    def raise_for_status(self) -> None: ...


class _YdlLogger:
    def __init__(self) -> None:
        self.lines: deque[str] = deque(maxlen=80)

    def _record(self, level: int, message: str) -> None:
        safe = redact_sensitive(message)
        self.lines.append(safe)
        logger.log(level, "yt-dlp: %s", safe)

    def debug(self, message: str) -> None:
        self._record(logging.DEBUG if message.startswith("[debug] ") else logging.INFO, message)

    def info(self, message: str) -> None:
        self._record(logging.INFO, message)

    def warning(self, message: str) -> None:
        self._record(logging.WARNING, message)

    def error(self, message: str) -> None:
        self._record(logging.ERROR, message)


class MediaResolver:
    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = ReadOnlyCookieYoutubeDL,
        http_get: Callable[..., _Response] = requests.get,
        deno_path: str | Path | None = None,
        require_deno: bool = True,
        network_policy: NetworkPolicy | None = None,
        cookie_profile=None,
        cookie_enabled: bool = False,
        ffmpeg_service: FfmpegService | None = None,
        metadata_language: str = '',
    ) -> None:
        self.ydl_factory = ydl_factory
        self.http_get = http_get
        self.deno_path = Path(deno_path) if deno_path else find_tool("deno")
        # Kept for older worker/config callers. The extractor decides whether
        # JavaScript is needed; non-YouTube media must not fail a global gate.
        self.require_deno = require_deno
        self.network_policy = network_policy
        self.cookie_profile = cookie_profile
        self.cookie_enabled = bool(cookie_enabled)
        self.ffmpeg_service = ffmpeg_service
        self.metadata_language = metadata_language
        self._media_probe_cache: dict[str, dict[str, Any]] = {}

    def fetch_metadata(
        self,
        url: str,
        cancel_event: threading.Event | None = None,
        *,
        include_thumbnail: bool = True,
    ) -> ResolvedMedia:
        try:
            normalized = normalize_media_url(url)
        except InvalidMediaUrl as exc:
            raise AppError("invalid_url", str(exc), str(exc), ErrorContext(url=url, stage="URL validation")) from exc
        if cancel_event and cancel_event.is_set():
            raise OperationCancelled(ErrorContext(url=normalized, stage="Fetching metadata"))
        ydl_logger = _YdlLogger()
        js_config: dict[str, dict[str, str]] = {"deno": {}}
        if self.deno_path:
            js_config["deno"]["path"] = str(self.deno_path)
        options: dict[str, Any] = {
            "ignoreconfig": True,
            "usenetrc": False,
            "cachedir": False,
            "allow_playlist_files": False,
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "lazy_playlist": True,
            "playlistend": 1001,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 10,
            "retries": 1,
            "fragment_retries": 1,
            "extractor_retries": 1,
            "logger": ydl_logger,
            "js_runtimes": js_config,
            "remote_components": [],
        }
        parsed_url = urlsplit(normalized)
        options.update(youtube_metadata_options(self.metadata_language))
        if parsed_url.hostname and parsed_url.hostname.casefold().endswith("bilibili.com") and "/video/" in parsed_url.path:
            # Bilibili replay video pages expose each segment's formats only in
            # yt-dlp's native playlist entries. Keep ordinary lists flat.
            options["extract_flat"] = False
        if self.network_policy:
            options.update(self.network_policy.ytdlp_options())
        try:
            try:
                options.update(cookie_options(self.cookie_profile))
            except ValueError as error:
                raise AppError('COOKIE_REQUIRED', str(error), 'Cookie profile validation failed') from None
            cookie_used = False
            with self.ydl_factory(options) as ydl:
                extracted = ydl.extract_info(normalized, download=False)
                if self.cookie_enabled and self.cookie_profile is not None:
                    cookiejar = getattr(ydl, 'cookiejar', None)
                    get_cookies = getattr(cookiejar, 'get_cookies_for_url', None)
                    if callable(get_cookies):
                        cookie_used = bool(get_cookies(normalized))
                # Bound the lazy enumeration; children are resolved only after selection.
                if isinstance(extracted, Mapping) and extracted.get('_type') in {'playlist', 'multi_video'}:
                    from itertools import islice
                    extracted = dict(extracted)
                    extracted['entries'] = list(islice(extracted.get('entries') or (), 1001))
                from yt_downloader.services.bilibili_bangumi import enrich_season
                extracted = enrich_season(ydl, extracted, normalized, cancel_event)
                info = ydl.sanitize_info(extracted)
                auth_state = detect_auth_state(
                    ydl, normalized, str(info.get('extractor_key') or info.get('extractor') or ''),
                    cookie_enabled=self.cookie_enabled, cookie_profile=self.cookie_profile)
            if cancel_event and cancel_event.is_set():
                raise OperationCancelled(ErrorContext(url=normalized, stage="Fetching metadata"))
            detected_formats = self._probe_missing_media_metadata(info, cancel_event)
            media = resolve_metadata(info, normalized, requested_url=url.strip(),
                                     detected_formats=detected_formats,
                                     cookie_used=cookie_used)
            if not media.formats and not media.audio_formats and media.media_type not in {'playlist', 'multi_video'}:
                raw_formats = info.get('formats')
                drm = info.get('has_drm') or any(item.get('has_drm') for item in (raw_formats or []) if isinstance(item, Mapping))
                raise AppError(
                    'DRM_UNSUPPORTED' if drm else 'APP_FORMAT_FILTER_ERROR' if raw_formats else 'NO_FORMATS',
                    '该媒体受 DRM 保护，无法处理。' if drm else '该媒体没有当前版本可下载的视频格式。',
                    'No usable video formats in extractor metadata',
                    ErrorContext(url=normalized, stage='Normalizing formats', log_excerpt='\n'.join(ydl_logger.lines)),
                )
            thumbnail_url = media.thumbnail_url
            thumbnail_bytes: bytes | None = None
            if thumbnail_url and include_thumbnail:
                if cancel_event and cancel_event.is_set():
                    raise OperationCancelled(ErrorContext(url=normalized, stage="Fetching thumbnail"))
                try:
                    request_get = self.network_policy.get if self.network_policy else self.http_get
                    response = request_get(thumbnail_url, timeout=20, headers={"User-Agent": "YTDownloader/0.2"})
                    if cancel_event and cancel_event.is_set():
                        raise OperationCancelled(ErrorContext(url=normalized, stage="Fetching thumbnail"))
                    response.raise_for_status()
                    thumbnail_bytes = bytes(response.content)
                except OperationCancelled:
                    raise
                except Exception as exc:  # Thumbnail failure is an optional capability failure.
                    logger.warning("Thumbnail download failed: %s", redact_sensitive(str(exc)))
            if cancel_event and cancel_event.is_set():
                raise OperationCancelled(ErrorContext(url=normalized, stage="Fetching metadata"))

            return replace(media, thumbnail_bytes=thumbnail_bytes, auth_state=auth_state)
        except OperationCancelled:
            raise
        except AppError:
            raise
        except (DownloadError, requests.RequestException, OSError, TypeError, ValueError) as exc:
            technical = redact_sensitive(str(exc))
            code, user_message = classify_metadata_error(exc)
            raise AppError(
                code,
                user_message,
                technical,
                ErrorContext(
                    url=normalized,
                    stage="Fetching metadata",
                    traceback_text=redact_sensitive(traceback.format_exc()),
                    log_excerpt="\n".join(ydl_logger.lines),
                ),
            ) from exc

    def _probe_missing_media_metadata(self, info: Mapping[str, Any], cancel_event=None) -> dict[str, dict[str, Any]]:
        formats = info.get("formats")
        # Collection pages can contain hundreds of unresolved entries. Probe only
        # formats yt-dlp resolved for this one media item, never playlist children.
        if (info.get("_type") in {"playlist", "multi_video"}
                or not isinstance(formats, list) or not formats):
            return {}
        unresolved = [item for item in formats if isinstance(item, Mapping) and needs_media_probe(item)]
        if not unresolved:
            return {}

        # Probe only one representative per native quality group, with a strict
        # cap for adaptive manifests that expose many aliases/bitrates.
        groups: dict[tuple[str, str], Mapping[str, Any]] = {}
        for item in unresolved:
            group = (str(item.get("quality") or item.get("format_note") or ""),
                     str(item.get("height") or item.get("width") or ""))
            groups.setdefault(group, item)
        selected = list(groups.values())[:4]
        results: dict[str, dict[str, Any]] = {}
        for item in selected:
            format_id = str(item.get("format_id") or "")
            key = probe_cache_key(item)
            if key not in self._media_probe_cache:
                self._media_probe_cache[key] = self._probe_one_media_format(item, cancel_event)
            results[format_id] = dict(self._media_probe_cache[key])
        return results

    def _probe_one_media_format(self, item: Mapping[str, Any], cancel_event=None) -> dict[str, Any]:
        if not self.ffmpeg_service:
            return {"source": "original"}
        headers = item.get("http_headers")
        # Deliberately carry only the same safe request context used by the
        # existing ffprobe adapter; Cookie/Authorization headers never reach logs.
        safe_headers = {str(key): str(value) for key, value in headers.items()
                        if str(key).casefold() in {"user-agent", "referer", "origin"}} if isinstance(headers, Mapping) else {}
        if cancel_event and cancel_event.is_set():
            raise OperationCancelled(ErrorContext(stage="Probing stream metadata"))
        try:
            detected = self.ffmpeg_service.probe_stream(str(item["url"]), http_headers=safe_headers, timeout=8)
        except OperationCancelled:
            raise
        except Exception as exc:
            logger.info("Optional media display probe failed (%s)", type(exc).__name__)
            return {"source": "original"}
        if not isinstance(detected, Mapping) or not detected.get("width") or not detected.get("height"):
            return {"source": "original"}
        detected = dict(detected)
        if detected.get("fps") is None:
            rate = detected.get("avg_frame_rate") or detected.get("r_frame_rate")
            try:
                numerator, denominator = str(rate).split("/", 1)
                detected["fps"] = float(numerator) / float(denominator)
            except (TypeError, ValueError, ZeroDivisionError):
                detected["fps"] = None
        return dict(detected, source="ffprobe")

    def fetch_thumbnail(
        self,
        thumbnail_url: str,
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        if cancel_event and cancel_event.is_set():
            raise OperationCancelled(ErrorContext(stage="Fetching thumbnail"))
        try:
            request_get = self.network_policy.get if self.network_policy else self.http_get
            response = request_get(
                thumbnail_url,
                timeout=10,
                headers={"User-Agent": "YTDownloader/0.3"},
            )
            if cancel_event and cancel_event.is_set():
                raise OperationCancelled(ErrorContext(stage="Fetching thumbnail"))
            response.raise_for_status()
            return bytes(response.content)
        except OperationCancelled:
            raise
        except Exception as exc:
            raise AppError(
                "thumbnail_failed",
                "视频信息已获取，但封面暂时无法加载。",
                redact_sensitive(repr(exc)),
                ErrorContext(stage="Fetching thumbnail"),
            ) from exc

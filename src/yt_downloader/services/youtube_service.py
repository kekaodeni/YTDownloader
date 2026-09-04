"""Metadata retrieval through yt-dlp's supported Python API."""

from __future__ import annotations

from collections import deque
import logging
from pathlib import Path
import threading
import traceback
from typing import Any, Callable, Mapping, Protocol

import requests
import yt_dlp
from yt_dlp.utils import DownloadError

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.core.formats import normalize_formats
from yt_downloader.core.models import CodecPreference, VideoInfo
from yt_downloader.core.url import InvalidYoutubeUrl, normalize_youtube_url
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.network_policy import NetworkPolicy


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


def _classify_metadata_error(message: str) -> tuple[str, str]:
    lowered = message.lower()
    if "429" in lowered or "too many requests" in lowered:
        return "rate_limited", "请求过于频繁，请稍后再试。"
    if "private video" in lowered or "video is private" in lowered:
        return "private_video", "该视频是私享视频，当前无法访问。"
    if "age" in lowered and ("restrict" in lowered or "confirm" in lowered):
        return "age_restricted", "该视频存在年龄限制，当前版本不支持登录验证。"
    if "not available in your country" in lowered or "geo" in lowered:
        return "region_restricted", "该视频在当前地区不可用。"
    if "403" in lowered or "forbidden" in lowered:
        return "forbidden", "YouTube 拒绝了请求，请稍后重试或更新 yt-dlp。"
    if "unsupported url" in lowered:
        return "unsupported_url", "该链接不是受支持的 YouTube 单视频地址。"
    return "metadata_failed", "无法获取该视频的信息。"


class YoutubeService:
    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = yt_dlp.YoutubeDL,
        http_get: Callable[..., _Response] = requests.get,
        deno_path: str | Path | None = None,
        require_deno: bool = True,
        network_policy: NetworkPolicy | None = None,
        codec_preference: CodecPreference = CodecPreference.AUTO,
    ) -> None:
        self.ydl_factory = ydl_factory
        self.http_get = http_get
        self.deno_path = Path(deno_path) if deno_path else find_tool("deno")
        self.require_deno = require_deno
        self.network_policy = network_policy
        self.codec_preference = codec_preference

    def fetch_metadata(
        self,
        url: str,
        cancel_event: threading.Event | None = None,
        *,
        include_thumbnail: bool = True,
    ) -> VideoInfo:
        try:
            normalized = normalize_youtube_url(url)
        except InvalidYoutubeUrl as exc:
            raise AppError("invalid_url", str(exc), str(exc), ErrorContext(url=url, stage="URL validation")) from exc
        if cancel_event and cancel_event.is_set():
            raise OperationCancelled(ErrorContext(url=normalized, stage="Fetching metadata"))
        if self.require_deno and (self.deno_path is None or not self.deno_path.is_file()):
            raise AppError(
                "deno_missing",
                "缺少内置 JavaScript 运行时，无法解析 YouTube 视频。",
                "Deno executable was not found",
                ErrorContext(url=normalized, stage="Fetching metadata"),
            )

        ydl_logger = _YdlLogger()
        js_config: dict[str, dict[str, str]] = {"deno": {}}
        if self.deno_path:
            js_config["deno"]["path"] = str(self.deno_path)
        options: dict[str, Any] = {
            "ignoreconfig": True,
            "noplaylist": True,
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
        if self.network_policy:
            options.update(self.network_policy.ytdlp_options())
        try:
            with self.ydl_factory(options) as ydl:
                extracted = ydl.extract_info(normalized, download=False)
                info = ydl.sanitize_info(extracted)
            if cancel_event and cancel_event.is_set():
                raise OperationCancelled(ErrorContext(url=normalized, stage="Fetching metadata"))
            if not isinstance(info, Mapping):
                raise TypeError("yt-dlp returned non-mapping metadata")
            raw_formats = info.get("formats") or []
            duration = float(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None
            formats = tuple(normalize_formats(
                raw_formats if isinstance(raw_formats, list) else [],
                duration=duration,
                codec_preference=self.codec_preference,
            ))
            if not formats:
                raise AppError(
                    "formats_unavailable",
                    "该视频没有可下载的画质。",
                    "yt-dlp metadata did not contain usable video formats",
                    ErrorContext(url=normalized, stage="Normalizing formats", log_excerpt="\n".join(ydl_logger.lines)),
                )

            thumbnail_url = str(info.get("thumbnail") or "") or None
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

            return VideoInfo(
                video_id=str(info.get("id") or normalized.rsplit("=", 1)[-1]),
                url=normalized,
                title=str(info.get("title") or "YouTube 视频"),
                channel=str(info.get("channel") or info.get("uploader") or "未知频道"),
                duration=duration,
                thumbnail_url=thumbnail_url,
                thumbnail_bytes=thumbnail_bytes,
                formats=formats,
                raw={
                    "id": str(info.get("id") or ""),
                    "webpage_url": normalized,
                    "extractor": str(info.get("extractor") or "youtube"),
                },
            )
        except OperationCancelled:
            raise
        except AppError:
            raise
        except (DownloadError, requests.RequestException, OSError, TypeError, ValueError) as exc:
            technical = redact_sensitive(str(exc))
            code, user_message = _classify_metadata_error(technical)
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

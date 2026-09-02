"""Safe yt-dlp downloads with truthful, throttled domain progress events."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from typing import Any, Callable

import yt_dlp
from yt_dlp.postprocessor import ffmpeg as ytdlp_ffmpeg
from yt_dlp.utils import DownloadError

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.core.filename import ensure_unique_path, sanitize_filename
from yt_downloader.core.models import DownloadProgress, DownloadRequest, DownloadResult, TaskStatus
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.ffmpeg_service import FfmpegService


logger = logging.getLogger(__name__)
_YTDLP_FFMPEG_PATCH_LOCK = threading.RLock()


def _cancellable_popen_type(cancel_event: threading.Event, context: ErrorContext):
    base = ytdlp_ffmpeg.Popen

    class CancellablePopen(base):
        @classmethod
        def run(cls, *args, timeout=None, input=None, **kwargs):
            if input is not None and kwargs.get("stdin") is None:
                kwargs["stdin"] = subprocess.PIPE
            started = time.monotonic()
            with cls(*args, **kwargs) as process:
                pending_input = input
                while True:
                    if cancel_event.is_set():
                        logger.info("Stopping task-owned FFmpeg process pid=%s", process.pid)
                        process.kill(timeout=None)
                        stdout, stderr = process.communicate()
                        logger.info(
                            "Task-owned FFmpeg process pid=%s stopped in %.3fs",
                            process.pid,
                            time.monotonic() - started,
                        )
                        raise OperationCancelled(context)
                    try:
                        stdout, stderr = process.communicate(input=pending_input, timeout=0.1)
                        default = "" if kwargs.get("text") or kwargs.get("encoding") else b""
                        return stdout or default, stderr or default, process.returncode
                    except subprocess.TimeoutExpired:
                        pending_input = None
                        if timeout is not None and time.monotonic() - started >= timeout:
                            process.kill(timeout=None)
                            stdout, stderr = process.communicate()
                            raise subprocess.TimeoutExpired(args[0] if args else None, timeout, stdout, stderr)

    return CancellablePopen


@contextmanager
def _interruptible_ytdlp_ffmpeg(cancel_event: threading.Event, context: ErrorContext):
    with _YTDLP_FFMPEG_PATCH_LOCK:
        original = ytdlp_ffmpeg.Popen
        ytdlp_ffmpeg.Popen = _cancellable_popen_type(cancel_event, context)
        try:
            yield
        finally:
            ytdlp_ffmpeg.Popen = original


class _DownloadLogger:
    def __init__(self) -> None:
        self.lines: deque[str] = deque(maxlen=120)

    def _write(self, level: int, message: str) -> None:
        safe = redact_sensitive(str(message))
        self.lines.append(safe)
        logger.log(level, "yt-dlp: %s", safe)

    def debug(self, message: str) -> None:
        self._write(logging.DEBUG if message.startswith("[debug] ") else logging.INFO, message)

    def info(self, message: str) -> None:
        self._write(logging.INFO, message)

    def warning(self, message: str) -> None:
        self._write(logging.WARNING, message)

    def error(self, message: str) -> None:
        self._write(logging.ERROR, message)


def _download_error(message: str) -> tuple[str, str]:
    lowered = message.lower()
    if "no space" in lowered or "disk full" in lowered:
        return "disk_full", "磁盘空间不足，无法完成下载。"
    if "429" in lowered or "too many requests" in lowered:
        return "rate_limited", "请求过于频繁，请稍后再试。"
    if "403" in lowered or "forbidden" in lowered:
        return "forbidden", "YouTube 拒绝了下载请求，请稍后重试或更新 yt-dlp。"
    if "ffmpeg" in lowered:
        return "ffmpeg_failed", "FFmpeg 处理视频失败。"
    if "requested format" in lowered:
        return "format_unavailable", "所选画质已不可用，请重新解析视频。"
    return "download_failed", "下载未能完成。"


class DownloadService:
    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = yt_dlp.YoutubeDL,
        deno_path: str | Path | None = None,
        ffmpeg_path: str | Path | None = None,
        require_tools: bool = True,
        media_validator: Callable[[Path], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ydl_factory = ydl_factory
        self.deno_path = Path(deno_path) if deno_path else find_tool("deno")
        self.ffmpeg_path = Path(ffmpeg_path) if ffmpeg_path else find_tool("ffmpeg")
        self.require_tools = require_tools
        self.clock = clock
        self.media_validator = media_validator

    @staticmethod
    def _validate_output_directory(directory: Path, required_bytes: int | None) -> None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".ytd-write-", dir=directory, delete=True):
                pass
        except OSError as exc:
            raise AppError(
                "output_unwritable",
                "下载目录不存在或不可写。",
                str(exc),
                ErrorContext(output_directory=str(directory), stage="Validating output"),
            ) from exc
        if required_bytes:
            free = shutil.disk_usage(directory).free
            reserve = max(64 * 1024 * 1024, int(required_bytes * 0.05))
            if free < required_bytes + reserve:
                raise AppError(
                    "disk_full",
                    "磁盘空间不足，无法开始下载。",
                    f"Required {required_bytes + reserve} bytes; available {free} bytes",
                    ErrorContext(output_directory=str(directory), stage="Validating disk space"),
                )

    def download(
        self,
        request: DownloadRequest,
        progress_callback: Callable[[DownloadProgress], None],
        cancel_event: threading.Event,
    ) -> DownloadResult:
        output_directory = request.output_directory.expanduser().resolve()
        context = ErrorContext(
            url=request.video.url,
            selected_format=request.format.label,
            output_directory=str(output_directory),
            stage="Preparing download",
        )
        if cancel_event.is_set():
            raise OperationCancelled(context)
        if self.require_tools:
            if not self.deno_path or not self.deno_path.is_file():
                raise AppError("deno_missing", "缺少内置 Deno，无法开始下载。", "Deno not found", context)
            if request.format.requires_merge and (not self.ffmpeg_path or not self.ffmpeg_path.is_file()):
                raise AppError("ffmpeg_missing", "缺少 FFmpeg，无法合并视频与音频。", "FFmpeg not found", context)

        self._validate_output_directory(output_directory, request.format.estimated_size)
        safe_stem = sanitize_filename(
            request.filename_stem,
            directory=output_directory,
            extension=f".{request.format.final_ext}",
        )
        final_path = ensure_unique_path(output_directory / f"{safe_stem}.{request.format.final_ext}")
        output_template = str(final_path.with_suffix(".%(ext)s"))
        ydl_logger = _DownloadLogger()
        last_emit_at = float("-inf")
        last_status: TaskStatus | None = None

        def emit(status: TaskStatus, data: dict[str, Any] | None = None, *, force: bool = False) -> None:
            nonlocal last_emit_at, last_status
            now = self.clock()
            if force and status == last_status:
                return
            if not force and status == last_status and now - last_emit_at < 0.1:
                return
            data = data or {}
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes")
            percent = None
            if isinstance(total, (int, float)) and total > 0 and isinstance(downloaded, (int, float)):
                percent = max(0.0, min(100.0, float(downloaded) * 100.0 / float(total)))
            progress_callback(DownloadProgress(
                task_id=request.task_id,
                status=status,
                percent=percent,
                downloaded_bytes=int(downloaded) if isinstance(downloaded, (int, float)) else None,
                total_bytes=int(total) if isinstance(total, (int, float)) else None,
                speed=float(data["speed"]) if isinstance(data.get("speed"), (int, float)) else None,
                eta=int(data["eta"]) if isinstance(data.get("eta"), (int, float)) else None,
            ))
            last_emit_at = now
            last_status = status

        def progress_hook(data: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise OperationCancelled(context)
            status = str(data.get("status") or "")
            if status == "downloading":
                format_id = str((data.get("info_dict") or {}).get("format_id") or "")
                stage = (
                    TaskStatus.DOWNLOADING_AUDIO
                    if request.format.audio_format_id and format_id == request.format.audio_format_id
                    else TaskStatus.DOWNLOADING_VIDEO
                )
                emit(stage, data)
            elif status == "finished":
                format_id = str((data.get("info_dict") or {}).get("format_id") or "")
                if request.format.audio_format_id and format_id == request.format.video_format_id:
                    emit(TaskStatus.DOWNLOADING_AUDIO, data, force=True)
                else:
                    emit(TaskStatus.MERGING if request.format.requires_merge else TaskStatus.POST_PROCESSING, data, force=True)

        def postprocessor_hook(data: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise OperationCancelled(context)
            name = str(data.get("postprocessor") or "")
            stage = TaskStatus.MERGING if "merger" in name.lower() and data.get("status") == "started" else TaskStatus.POST_PROCESSING
            emit(stage, data, force=True)

        js_config: dict[str, dict[str, str]] = {"deno": {}}
        if self.deno_path:
            js_config["deno"]["path"] = str(self.deno_path)
        options: dict[str, Any] = {
            "ignoreconfig": True,
            "noplaylist": True,
            "continuedl": True,
            "overwrites": False,
            "nopart": False,
            "format": request.format.format_selector,
            "outtmpl": {"default": output_template},
            "merge_output_format": request.format.final_ext,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "logger": ydl_logger,
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": js_config,
            "remote_components": [],
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 5,
            "ffmpeg_location": str(self.ffmpeg_path.parent) if self.ffmpeg_path else None,
            # Kept private to this app; test doubles use it without parsing an output template.
            "final_path": str(final_path),
        }
        try:
            with _interruptible_ytdlp_ffmpeg(cancel_event, context):
                with self.ydl_factory(options) as ydl:
                    exit_code = ydl.download([request.video.url])
            if cancel_event.is_set():
                raise OperationCancelled(context)
            if exit_code:
                raise DownloadError(f"yt-dlp returned exit code {exit_code}")
            if not final_path.is_file():
                candidates = sorted(
                    output_directory.glob(f"{final_path.stem}.*"),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )
                final_path = next((item for item in candidates if item.suffix != ".part"), final_path)
            if not final_path.is_file():
                raise OSError(f"Expected output was not created: {final_path}")

            validator = self.media_validator
            if validator is None and self.ffmpeg_path:
                validator = FfmpegService(ffmpeg_path=self.ffmpeg_path).has_audio_and_video
            if validator and not validator(final_path):
                raise AppError(
                    "media_validation_failed",
                    "下载完成，但文件没有同时包含视频和音频流。",
                    "ffprobe stream validation failed",
                    context,
                )
            emit(TaskStatus.COMPLETED, {"downloaded_bytes": final_path.stat().st_size, "total_bytes": final_path.stat().st_size}, force=True)
            return DownloadResult(
                request.task_id,
                final_path,
                final_path.stat().st_size,
                datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            )
        except OperationCancelled:
            raise
        except AppError:
            raise
        except Exception as exc:
            if cancel_event.is_set():
                raise OperationCancelled(context) from exc
            technical = redact_sensitive(str(exc))
            code, user_message = _download_error(technical)
            raise AppError(
                code,
                user_message,
                technical,
                ErrorContext(
                    url=context.url,
                    selected_format=context.selected_format,
                    output_directory=context.output_directory,
                    stage="Downloading",
                    traceback_text=redact_sensitive(traceback.format_exc()),
                    log_excerpt="\n".join(ydl_logger.lines),
                ),
            ) from exc

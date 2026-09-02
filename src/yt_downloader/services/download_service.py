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
from yt_downloader.services.network_policy import NetworkPolicy
from yt_downloader.services.download_tuning import AUTO_FRAGMENT_COUNT


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
        network_policy: NetworkPolicy | None = None,
        concurrent_fragments: int = 0,
    ) -> None:
        self.ydl_factory = ydl_factory
        self.deno_path = Path(deno_path) if deno_path else find_tool("deno")
        self.ffmpeg_path = Path(ffmpeg_path) if ffmpeg_path else find_tool("ffmpeg")
        self.require_tools = require_tools
        self.clock = clock
        self.media_validator = media_validator
        self.network_policy = network_policy
        if concurrent_fragments not in {0, 1, 2, 4, 8}:
            raise ValueError("concurrent_fragments must be auto (0), 1, 2, 4, or 8")
        self.concurrent_fragments = concurrent_fragments

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
        expected_format_ids = {request.format.video_format_id}
        if request.format.audio_format_id:
            expected_format_ids.add(request.format.audio_format_id)
        component_downloaded: dict[str, int] = {}
        component_totals: dict[str, int] = {}
        component_total_is_estimate: dict[str, bool] = {}
        locked_total = request.format.estimated_size
        locked_total_is_estimate = request.format.size_is_estimate
        last_aggregate_downloaded: int | None = None

        def aggregate_transfer(data: dict[str, Any], *, finished: bool = False) -> tuple[int | None, int | None, bool]:
            nonlocal locked_total, locked_total_is_estimate, last_aggregate_downloaded
            info = data.get("info_dict") or {}
            format_id = str(info.get("format_id") or "")
            if not format_id and len(expected_format_ids) == 1:
                format_id = next(iter(expected_format_ids))
            if format_id:
                downloaded = data.get("downloaded_bytes")
                if isinstance(downloaded, (int, float)) and downloaded >= 0:
                    component_downloaded[format_id] = max(component_downloaded.get(format_id, 0), int(downloaded))
                total = data.get("total_bytes")
                estimate = data.get("total_bytes_estimate")
                if isinstance(total, (int, float)) and total > 0:
                    component_totals[format_id] = int(total)
                    component_total_is_estimate[format_id] = False
                elif isinstance(estimate, (int, float)) and estimate > 0:
                    component_totals[format_id] = int(estimate)
                    component_total_is_estimate[format_id] = True
                if finished and format_id in component_totals:
                    component_downloaded[format_id] = max(
                        component_downloaded.get(format_id, 0),
                        component_totals[format_id],
                    )
            aggregate = sum(component_downloaded.values()) if component_downloaded else None
            if aggregate is not None:
                last_aggregate_downloaded = max(last_aggregate_downloaded or 0, aggregate)
            if locked_total is None and expected_format_ids.issubset(component_totals):
                locked_total = sum(component_totals[item] for item in expected_format_ids)
                locked_total_is_estimate = any(component_total_is_estimate[item] for item in expected_format_ids)
            return last_aggregate_downloaded, locked_total, locked_total_is_estimate

        def emit(
            status: TaskStatus,
            data: dict[str, Any] | None = None,
            *,
            force: bool = False,
            finished_component: bool = False,
        ) -> None:
            nonlocal last_emit_at, last_status
            now = self.clock()
            data = data or {}
            downloaded, total, total_is_estimate = aggregate_transfer(data, finished=finished_component)
            if force and status == last_status:
                return
            if not force and status == last_status and now - last_emit_at < 0.1:
                return
            percent = None
            if total and downloaded is not None:
                percent = max(0.0, min(100.0, float(downloaded) * 100.0 / float(total)))
            progress_callback(DownloadProgress(
                task_id=request.task_id,
                status=status,
                percent=percent,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=float(data["speed"]) if isinstance(data.get("speed"), (int, float)) else None,
                eta=int(data["eta"]) if isinstance(data.get("eta"), (int, float)) else None,
                total_is_estimate=total_is_estimate,
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
                    emit(TaskStatus.DOWNLOADING_AUDIO, data, force=True, finished_component=True)
                else:
                    emit(
                        TaskStatus.MERGING if request.format.requires_merge else TaskStatus.POST_PROCESSING,
                        data,
                        force=True,
                        finished_component=True,
                    )

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
            "concurrent_fragment_downloads": self.concurrent_fragments or AUTO_FRAGMENT_COUNT,
            "ffmpeg_location": str(self.ffmpeg_path.parent) if self.ffmpeg_path else None,
            # Kept private to this app; test doubles use it without parsing an output template.
            "final_path": str(final_path),
        }
        if self.network_policy:
            options.update(self.network_policy.ytdlp_options())
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
            final_size = final_path.stat().st_size
            progress_callback(DownloadProgress(
                request.task_id,
                TaskStatus.COMPLETED,
                100.0,
                final_size,
                final_size,
                total_is_estimate=False,
            ))
            return DownloadResult(
                request.task_id,
                final_path,
                final_size,
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

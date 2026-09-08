"""Safe yt-dlp downloads with truthful, throttled domain progress events."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import gc
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
from yt_dlp.downloader.fragment import FragmentFD
from yt_dlp.postprocessor import ffmpeg as ytdlp_ffmpeg
from yt_dlp.utils import DownloadError

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.core.filename import ensure_unique_path, sanitize_filename
from yt_downloader.core.models import (
    DownloadProgress,
    DownloadRequest,
    DownloadResult,
    ProgressTotalSource,
    TaskStatus,
)
from yt_downloader.core.progress import AggregateProgressTracker
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.network_policy import NetworkPolicy
from yt_downloader.services.download_tuning import AUTO_FRAGMENT_COUNT
from yt_downloader.services.task_artifacts import TaskArtifactRegistry


logger = logging.getLogger(__name__)
_YTDLP_RESOURCE_PATCH_LOCK = threading.RLock()


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


class _InterruptibleYtdlpResources:
    """Temporarily patch yt-dlp's FFmpeg process without rewriting exceptions.

    ``contextlib.contextmanager`` assigns ``__traceback__`` while unwinding.
    Domain errors are frozen dataclasses, so that assignment can replace the
    original cancellation with a ``TypeError``.  A regular context manager
    restores the process type and lets the original exception pass through.
    """

    def __init__(self, cancel_event: threading.Event, context: ErrorContext) -> None:
        self.cancel_event = cancel_event
        self.context = context
        self.original: type | None = None
        self.original_fragment_download: Callable[..., Any] | None = None

    def __enter__(self) -> "_InterruptibleYtdlpResources":
        _YTDLP_RESOURCE_PATCH_LOCK.acquire()
        try:
            self.original = ytdlp_ffmpeg.Popen
            self.original_fragment_download = FragmentFD.download_and_append_fragments
            ytdlp_ffmpeg.Popen = _cancellable_popen_type(self.cancel_event, self.context)
            original_fragment_download = self.original_fragment_download
            cancel_event = self.cancel_event

            def cancellable_fragment_download(
                downloader,
                fragment_context,
                *args,
                **kwargs,
            ):
                try:
                    return original_fragment_download(
                        downloader,
                        fragment_context,
                        *args,
                        **kwargs,
                    )
                except BaseException:
                    if cancel_event.is_set():
                        destination = fragment_context.get("dest_stream")
                        if destination is not None and not getattr(destination, "closed", True):
                            try:
                                destination.close()
                            except OSError as close_error:
                                logger.warning(
                                    "Unable to close task-owned fragment stream: %s",
                                    close_error,
                                )
                    raise

            FragmentFD.download_and_append_fragments = cancellable_fragment_download
        except BaseException:
            if self.original is not None:
                ytdlp_ffmpeg.Popen = self.original
            if self.original_fragment_download is not None:
                FragmentFD.download_and_append_fragments = self.original_fragment_download
            _YTDLP_RESOURCE_PATCH_LOCK.release()
            raise
        return self

    def __exit__(self, exc_type, exc, traceback_object) -> bool:
        try:
            if self.original is not None:
                ytdlp_ffmpeg.Popen = self.original
            if self.original_fragment_download is not None:
                FragmentFD.download_and_append_fragments = self.original_fragment_download
        finally:
            _YTDLP_RESOURCE_PATCH_LOCK.release()
        return False


def _interruptible_ytdlp_resources(
    cancel_event: threading.Event,
    context: ErrorContext,
) -> _InterruptibleYtdlpResources:
    return _InterruptibleYtdlpResources(cancel_event, context)


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


def _release_cancelled_stack_resources(error: BaseException) -> None:
    """Drop exited stack-frame locals before deleting task-owned artifacts.

    yt-dlp's fragmented downloader does not close its destination stream when
    a progress hook raises.  The exited frame (and therefore the open stream)
    remains reachable through the exception traceback until that traceback is
    collected.  Clearing exited frames releases the handle deterministically;
    the currently executing service frame is intentionally left alone by the
    standard-library helper.
    """

    if error.__traceback__ is not None:
        traceback.clear_frames(error.__traceback__)
    # yt-dlp's fragment context and its progress-hook closure form a cycle
    # containing the destination stream.  Collect it before bounded deletion
    # retries so Windows no longer sees the task-owned .part file as open.
    gc.collect()


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
        destination = ensure_unique_path(output_directory / f"{safe_stem}.{request.format.final_ext}")
        artifacts = TaskArtifactRegistry(output_directory, request.task_id)
        artifacts.prepare()
        final_path = artifacts.download_path(request.format.final_ext)
        output_template = artifacts.output_template
        ydl_logger = _DownloadLogger()
        last_emit_at = float("-inf")
        last_status: TaskStatus | None = None
        aggregate_progress = AggregateProgressTracker(request.format)
        smoothed_speed: float | None = None
        last_speed_at: float | None = None

        def emit(
            status: TaskStatus,
            data: dict[str, Any] | None = None,
            *,
            force: bool = False,
            finished_component: bool = False,
        ) -> None:
            nonlocal last_emit_at, last_status, smoothed_speed, last_speed_at
            now = self.clock()
            data = data or {}
            snapshot = aggregate_progress.update(data, finished=finished_component)
            if force and status == last_status:
                return
            if not force and status == last_status and now - last_emit_at < 0.08:
                return
            if status in {TaskStatus.MERGING, TaskStatus.POST_PROCESSING}:
                snapshot = aggregate_progress.terminal_stage_snapshot()
            downloaded = snapshot.downloaded_bytes
            total = snapshot.total_bytes
            percent = None
            if total and downloaded is not None:
                # A native fragment estimate may temporarily equal bytes read.
                # Reserve 100% for the provider's finished/processing stage.
                ceiling = 99.0 if status in {TaskStatus.DOWNLOADING_VIDEO, TaskStatus.DOWNLOADING_AUDIO} else 100.0
                percent = max(0.0, min(ceiling, float(downloaded) * 100.0 / float(total)))
            raw_speed = float(data["speed"]) if isinstance(data.get("speed"), (int, float)) and data["speed"] > 0 else None
            if raw_speed is not None:
                smoothed_speed = raw_speed if smoothed_speed is None else (0.25 * raw_speed) + (0.75 * smoothed_speed)
                last_speed_at = now
            provider_eta = data.get("eta")
            eta = int(provider_eta) if isinstance(provider_eta, (int, float)) and provider_eta >= 0 else None
            if (
                eta is None
                and total is not None
                and not snapshot.total_is_estimate
                and downloaded is not None
                and smoothed_speed
                and last_speed_at is not None
                and now - last_speed_at <= 3.0
            ):
                eta = max(0, round((total - downloaded) / smoothed_speed))
            progress_callback(DownloadProgress(
                task_id=request.task_id,
                status=status,
                percent=percent,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=raw_speed,
                eta=eta,
                total_is_estimate=snapshot.total_is_estimate,
                total_source=snapshot.total_source,
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
            with _interruptible_ytdlp_resources(cancel_event, context):
                with self.ydl_factory(options) as ydl:
                    exit_code = ydl.download([request.video.url])
            if cancel_event.is_set():
                raise OperationCancelled(context)
            if exit_code:
                raise DownloadError(f"yt-dlp returned exit code {exit_code}")
            if not final_path.is_file():
                final_path = artifacts.find_completed_file(request.format.final_ext) or final_path
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
            final_path = artifacts.commit(final_path, destination)
            cleanup_report = artifacts.cleanup()
            if not cleanup_report.succeeded:
                logger.error(
                    "Download completed but task workspace cleanup failed: %s",
                    cleanup_report.failed_paths,
                )
            final_size = final_path.stat().st_size
            progress_callback(DownloadProgress(
                request.task_id,
                TaskStatus.COMPLETED,
                100.0,
                final_size,
                final_size,
                total_is_estimate=False,
                total_source=ProgressTotalSource.FINAL,
            ))
            return DownloadResult(
                request.task_id,
                final_path,
                final_size,
                datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            )
        except OperationCancelled as exc:
            cancellation_context = exc.context or context
            _release_cancelled_stack_resources(exc)
            cleanup_report = artifacts.cleanup()
            raise OperationCancelled(cancellation_context, cleanup_report) from None
        except AppError:
            raise
        except Exception as exc:
            if cancel_event.is_set():
                _release_cancelled_stack_resources(exc)
                cleanup_report = artifacts.cleanup()
                raise OperationCancelled(context, cleanup_report) from None
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

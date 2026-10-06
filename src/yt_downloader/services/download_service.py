"""Safe yt-dlp downloads with truthful, throttled domain progress events."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from dataclasses import replace
import gc
import logging
import re
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
from yt_dlp.downloader import external as ytdlp_external
from yt_dlp.postprocessor import ffmpeg as ytdlp_ffmpeg
from yt_dlp.utils import DownloadError

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled, OperationPaused
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
from yt_downloader.services.download_options import media_options, prepare_request
from yt_downloader.services.subtitle_service import SubtitleService, SubtitleResult
from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL, cookie_options
from yt_downloader.services.section_progress import SectionDownloadProgressAdapter, observed_section_popen, is_section_ffmpeg
from yt_downloader.services.media_errors import classify_download_error as _download_error


logger = logging.getLogger(__name__)
_YTDLP_RESOURCE_PATCH_LOCK = threading.RLock()
_YTDLP_TASK_CONTEXT = threading.local()
_YTDLP_PATCH_USERS = 0
_YTDLP_ORIGINAL_POPEN = None
_YTDLP_ORIGINAL_FRAGMENT = None
_YTDLP_ORIGINAL_EXTERNAL_POPEN = None


def _cancellable_popen_type(cancel_event: threading.Event, context: ErrorContext, base=None):
    base = base or ytdlp_ffmpeg.Popen

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
    """Share temporary dispatchers, while cancellation belongs to each task thread."""

    def __init__(self, cancel_event: threading.Event, context: ErrorContext, section=None) -> None:
        self.task = (cancel_event, context, section)
        self.previous = None

    def __enter__(self):
        global _YTDLP_PATCH_USERS, _YTDLP_ORIGINAL_POPEN, _YTDLP_ORIGINAL_FRAGMENT
        global _YTDLP_ORIGINAL_EXTERNAL_POPEN
        with _YTDLP_RESOURCE_PATCH_LOCK:
            if _YTDLP_PATCH_USERS == 0:
                original = ytdlp_ffmpeg.Popen
                original_fragment = FragmentFD.download_and_append_fragments
                original_external = ytdlp_external.Popen

                class TaskPopen(original):
                    @classmethod
                    def run(cls, *args, **kwargs):
                        task = getattr(_YTDLP_TASK_CONTEXT, 'task', None)
                        if task is None:
                            return original.run(*args, **kwargs)
                        return _cancellable_popen_type(*task[:2], base=original).run(*args, **kwargs)

                class TaskExternalPopen(original_external):
                    def __new__(cls, args, *remaining, **kwargs):
                        task = getattr(_YTDLP_TASK_CONTEXT, 'task', None)
                        if task and task[2] is not None and is_section_ffmpeg(args):
                            observed = observed_section_popen(original_external, task[2], task[0], task[1])
                            return observed(args, *remaining, **kwargs)
                        return super().__new__(cls)

                def fragment_download(downloader, fragment_context, *args, **kwargs):
                    task = getattr(_YTDLP_TASK_CONTEXT, 'task', None)
                    try:
                        return original_fragment(downloader, fragment_context, *args, **kwargs)
                    except BaseException:
                        if task and task[0].is_set():
                            destination = fragment_context.get('dest_stream')
                            if destination is not None and not getattr(destination, 'closed', True):
                                try:
                                    destination.close()
                                except OSError as error:
                                    logger.warning('Unable to close task-owned fragment stream: %s', error)
                        raise

                _YTDLP_ORIGINAL_POPEN = original
                _YTDLP_ORIGINAL_FRAGMENT = original_fragment
                _YTDLP_ORIGINAL_EXTERNAL_POPEN = original_external
                ytdlp_ffmpeg.Popen = TaskPopen
                ytdlp_external.Popen = TaskExternalPopen
                FragmentFD.download_and_append_fragments = fragment_download
            _YTDLP_PATCH_USERS += 1
            self.previous = getattr(_YTDLP_TASK_CONTEXT, 'task', None)
            _YTDLP_TASK_CONTEXT.task = self.task
        return self

    def __exit__(self, exc_type, exc, traceback_object):
        global _YTDLP_PATCH_USERS
        with _YTDLP_RESOURCE_PATCH_LOCK:
            _YTDLP_TASK_CONTEXT.task = self.previous
            _YTDLP_PATCH_USERS -= 1
            if _YTDLP_PATCH_USERS == 0:
                ytdlp_ffmpeg.Popen = _YTDLP_ORIGINAL_POPEN
                ytdlp_external.Popen = _YTDLP_ORIGINAL_EXTERNAL_POPEN
                FragmentFD.download_and_append_fragments = _YTDLP_ORIGINAL_FRAGMENT
        return False


def _interruptible_ytdlp_resources(
    cancel_event: threading.Event,
    context: ErrorContext,
    section=None,
) -> _InterruptibleYtdlpResources:
    return _InterruptibleYtdlpResources(cancel_event, context, section)


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


# Compatibility name for existing callers and focused regressions.


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
        ydl_factory: Callable[[dict[str, Any]], Any] = ReadOnlyCookieYoutubeDL,
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
        if request.resolve_before_download:
            from yt_downloader.services.media_resolver import MediaResolver
            progress_callback(DownloadProgress(request.task_id, TaskStatus.FETCHING_METADATA))
            media = MediaResolver(deno_path=self.deno_path, require_deno=self.require_tools,
                                  network_policy=self.network_policy, cookie_profile=request.cookie_profile,
                                  metadata_language=request.metadata_language).fetch_metadata(
                                      request.video.url, cancel_event, include_thumbnail=False)
            options = media.audio_formats if request.media_mode == 'audio_only' else media.video_only_formats if request.media_mode == 'video_only' else media.formats
            if media.media_type == 'playlist' or not options:
                raise AppError('formats_unavailable', '此项目没有所选模式可用的格式。', 'Batch child has no matching single-media format')
            from yt_downloader.core.formats import apply_codec_preference
            options = tuple(apply_codec_preference(option, request.codec_preference) for option in options)
            from yt_downloader.core.quality_target import choose_quality
            option = choose_quality(options, request.preferred_quality)
            if request.video.canonical_thumbnail_url or request.video.collection_thumbnail_url:
                media = replace(media,
                                canonical_thumbnail_url=request.video.canonical_thumbnail_url,
                                collection_thumbnail_url=request.video.collection_thumbnail_url,
                                thumbnail_url=request.video.canonical_thumbnail_url or media.thumbnail_url
                                              or request.video.collection_thumbnail_url or None,
                                thumbnail_bytes=None)
            progress_callback(DownloadProgress(request.task_id, TaskStatus.FETCHING_METADATA,
                                              resolved_quality=f'{option.label} · {option.container}',
                                              resolved_thumbnail_url=media.thumbnail_url or '',
                                              resolved_thumbnail_bytes=media.thumbnail_bytes))
            request = replace(request, video=media, format=option, resolve_before_download=False)
        request = prepare_request(request)
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
            needs_ffmpeg = (request.format.requires_merge or request.use_native_format or request.audio_codec != 'original'
                            or request.embed_thumbnail or request.embed_metadata or request.embed_chapters
                            or bool(request.remux_container) or request.sponsorblock_mark)
            if needs_ffmpeg and (not self.ffmpeg_path or not self.ffmpeg_path.is_file()):
                raise AppError("ffmpeg_missing", "缺少 FFmpeg，无法合并视频与音频。", "FFmpeg not found", context)

        self._validate_output_directory(output_directory, request.format.estimated_size)
        safe_stem = sanitize_filename(
            request.filename_stem,
            directory=output_directory,
            extension=f".{request.format.final_ext}",
        )
        final_extension = request.remux_container or request.format.final_ext
        destination = ensure_unique_path(output_directory / f"{safe_stem}.{final_extension}")
        artifacts = TaskArtifactRegistry(output_directory, request.task_id)
        artifacts.prepare(resume_existing=request.resume_partial)
        final_path = artifacts.download_path(request.format.final_ext)
        output_template = artifacts.output_template
        ydl_logger = _DownloadLogger()
        last_emit_at = float("-inf")
        last_status: TaskStatus | None = None
        aggregate_progress = AggregateProgressTracker(request.format)
        section = None
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
            if section is not None and section.latest is not None and status in {TaskStatus.MERGING, TaskStatus.POST_PROCESSING}:
                if force and status == last_status:
                    return
                progress_callback(replace(section.latest, status=status, percent=100.0, speed=None, eta=None))
                last_emit_at, last_status = now, status
                return
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
                    if request.media_mode == 'audio_only' or (request.format.audio_format_id and format_id == request.format.audio_format_id)
                    else TaskStatus.DOWNLOADING_VIDEO
                )
                emit(stage, data)
            elif status == "finished":
                if section is not None and section.latest is not None:
                    section.finished(data)
                    # Native FFmpegFD has already muxed the selected inputs.
                    emit(TaskStatus.POST_PROCESSING, force=True)
                    return
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
            nonlocal request
            if cancel_event.is_set():
                raise OperationCancelled(context)
            name = str(data.get("postprocessor") or "")
            if name == 'CollectionCover':
                return  # Metadata-only preparation isn't media post-processing.
            if name == 'EmbedThumbnail' and data.get('status') == 'started':
                selected = next((item for item in reversed((data.get('info_dict') or {}).get('thumbnails') or [])
                                 if item.get('filepath')), None)
                if selected:
                    path = Path(selected['filepath'])
                    if path.is_file() and path.stat().st_size <= 32 * 1024 * 1024:
                        request = replace(request, video=replace(request.video,
                                          thumbnail_url=selected['url'], thumbnail_bytes=path.read_bytes()))
            stage = TaskStatus.MERGING if "merger" in name.lower() and data.get("status") == "started" else TaskStatus.POST_PROCESSING
            emit(stage, data, force=True)

        js_config: dict[str, dict[str, str]] = {"deno": {}}
        if self.deno_path:
            js_config["deno"]["path"] = str(self.deno_path)
        options: dict[str, Any] = {
            "ignoreconfig": True,
            "usenetrc": False,
            "cachedir": False,
            "noplaylist": True,
            "continuedl": True,
            "overwrites": False,
            "nopart": False,
            "outtmpl": {"default": output_template},
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
        options.update(media_options(request))
        from yt_downloader.services.metadata_language import youtube_metadata_options
        options.update(youtube_metadata_options(request.metadata_language))
        if request.embed_thumbnail:
            # Download only the child video's image, not a playlist parent cover.
            options['outtmpl']['pl_thumbnail'] = ''
        if request.playlist_item_index is not None:
            options['noplaylist'] = False
        if self.network_policy:
            options.update(self.network_policy.ytdlp_options())
        try:
            try:
                options.update(cookie_options(request.cookie_profile))
            except ValueError as error:
                raise AppError('COOKIE_REQUIRED', str(error), 'Cookie profile validation failed') from None
            def section_progress(progress):
                nonlocal last_emit_at, last_status
                progress_callback(progress)
                last_emit_at, last_status = self.clock(), progress.status

            section = SectionDownloadProgressAdapter(request, section_progress, log=ydl_logger.warning,
                                                     clock=self.clock) if request.clip_enabled else None
            with _interruptible_ytdlp_resources(cancel_event, context, section):
                with self.ydl_factory(options) as ydl:
                    if request.embed_thumbnail and (request.video.canonical_thumbnail_url or request.video.collection_thumbnail_url):
                        from yt_downloader.services.collection_cover import CollectionCoverPP
                        ydl.add_post_processor(CollectionCoverPP(ydl, request.video.canonical_thumbnail_url,
                                                                 request.video.collection_thumbnail_url), when='video')
                    if section is not None:
                        section.proxies = getattr(ydl, 'proxies', None)
                    exit_code = ydl.download([request.video.url])
            if getattr(cancel_event, 'is_paused', lambda: False)() and not getattr(cancel_event, 'is_cancelled', lambda: False)():
                raise OperationPaused(context)
            if cancel_event.is_set():
                raise OperationCancelled(context)
            if exit_code:
                raise DownloadError(f"yt-dlp returned exit code {exit_code}")
            if request.use_native_format or request.remux_container or not final_path.is_file():
                final_path = artifacts.find_completed_file(final_extension) or final_path
            if not final_path.is_file():
                raise OSError(f"Expected output was not created: {final_path}")
            if request.use_native_format:
                # The native selector may choose a different container from
                # the UI's illustrative quality. Keep the real extension.
                destination = ensure_unique_path(output_directory / f"{safe_stem}{final_path.suffix}")

            validator = self.media_validator
            if validator is None and self.ffmpeg_path:
                validator = lambda path: FfmpegService(ffmpeg_path=self.ffmpeg_path).has_media_streams(path, request.media_mode)
            if validator and not validator(final_path):
                raise AppError(
                    "media_validation_failed",
                    "下载完成，但文件中的音视频流与所选下载模式不一致。",
                    "ffprobe stream validation failed",
                    context,
                )
            subtitles = SubtitleResult(final_path)
            if request.subtitle_enabled:
                try:
                    subtitles = SubtitleService(self.ffmpeg_path, self.network_policy).process(
                        request, final_path, artifacts.workspace, cancel_event)
                except OperationCancelled:
                    raise
                except Exception:
                    subtitles = SubtitleResult(final_path, warnings=('字幕处理失败，媒体已保留。',))
            final_path = artifacts.commit(subtitles.media, destination)
            subtitle_paths = []
            for language, path in subtitles.files:
                try:
                    subtitle_paths.append(artifacts.commit(path, final_path.with_suffix(f'.{language}.{request.subtitle_format}')))
                except OSError:
                    subtitles = SubtitleResult(final_path, warnings=(*subtitles.warnings, '字幕文件保存失败，媒体已保留。'))
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
                warnings=subtitles.warnings, subtitle_paths=tuple(subtitle_paths),
                subtitle_embedded=subtitles.embedded, subtitle_auto_used=subtitles.auto_used,
                resolved_media=request.video, resolved_format=request.format,
            )
        except OperationPaused as exc:
            _release_cancelled_stack_resources(exc)
            raise
        except OperationCancelled as exc:
            cancellation_context = exc.context or context
            _release_cancelled_stack_resources(exc)
            if getattr(cancel_event, 'is_paused', lambda: False)() and not getattr(cancel_event, 'is_cancelled', lambda: False)():
                raise OperationPaused(cancellation_context) from None
            cleanup_report = artifacts.cleanup()
            raise OperationCancelled(cancellation_context, cleanup_report) from None
        except AppError:
            raise
        except Exception as exc:
            if cancel_event.is_set():
                _release_cancelled_stack_resources(exc)
                if getattr(cancel_event, 'is_paused', lambda: False)() and not getattr(cancel_event, 'is_cancelled', lambda: False)():
                    raise OperationPaused(context) from None
                cleanup_report = artifacts.cleanup()
                raise OperationCancelled(context, cleanup_report) from None
            technical = redact_sensitive(str(exc))
            ffmpeg_stderr = '\n'.join(line for line in ydl_logger.lines if line.startswith('FFmpeg:'))
            code, user_message = _download_error(technical + '\n' + ffmpeg_stderr)
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

"""Safe, cancellable FFmpeg and ffprobe subprocess integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Callable
import uuid

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.infrastructure.runtime import find_tool


_OUTPUT_LIMIT = 64 * 1024
logger = logging.getLogger(__name__)
_COVER_CONTAINERS = {".mp4", ".m4v", ".mov"}
_VOLATILE_FORMAT_TAGS = {"encoder", "major_brand", "minor_version", "compatible_brands"}


class ExplorerCoverStatus(StrEnum):
    MATCHED = "matched"
    NOT_USED = "not_used"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CoverEmbedResult:
    file_path: Path
    media_validated: bool
    explorer_status: ExplorerCoverStatus
    message: str


def validate_timestamp(timestamp: float, duration: float) -> float:
    value = float(timestamp)
    total = float(duration)
    if not math.isfinite(value) or not math.isfinite(total) or total < 0 or value < 0 or value > total:
        raise ValueError("缩略图时间必须位于视频时长范围内。")
    return value


class FfmpegService:
    def __init__(
        self,
        ffmpeg_path: str | Path | None = None,
        ffprobe_path: str | Path | None = None,
        *,
        configured_directory: str | Path | None = None,
        shell_thumbnail_checker: Callable[[Path, Path], bool | None] | None = None,
    ) -> None:
        self.ffmpeg_path = Path(ffmpeg_path) if ffmpeg_path else find_tool("ffmpeg", configured_directory)
        self.ffprobe_path = Path(ffprobe_path) if ffprobe_path else find_tool("ffprobe", configured_directory)
        self.shell_thumbnail_checker = shell_thumbnail_checker

    @property
    def available(self) -> bool:
        return bool(self.ffmpeg_path and self.ffmpeg_path.is_file() and self.ffprobe_path and self.ffprobe_path.is_file())

    def _require(self, path: Path | None, tool: str) -> Path:
        if path is None or not path.is_file():
            raise AppError(
                code=f"{tool}_missing",
                user_message=f"未找到 {tool}，无法处理视频。",
                technical_message=f"{tool} executable was not found",
            )
        return path

    def _run(
        self,
        arguments: list[str],
        *,
        cancel_event: threading.Event | None = None,
        timeout: float = 60,
        stage: str = "FFmpeg",
    ) -> subprocess.CompletedProcess[str]:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                arguments,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
        except OSError as exc:
            raise AppError(
                code="ffmpeg_start_failed",
                user_message="无法启动视频处理工具。",
                technical_message=str(exc),
                context=ErrorContext(stage=stage),
            ) from exc

        deadline = time.monotonic() + timeout
        stdout = stderr = ""
        while True:
            if cancel_event and cancel_event.is_set():
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                raise OperationCancelled(ErrorContext(stage=stage))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                stdout, stderr = process.communicate()
                raise AppError(
                    code="ffmpeg_timeout",
                    user_message="视频处理超时。",
                    technical_message=stderr[-_OUTPUT_LIMIT:] or f"Timed out after {timeout}s",
                    context=ErrorContext(stage=stage),
                )
            try:
                stdout, stderr = process.communicate(timeout=min(0.2, remaining))
                break
            except subprocess.TimeoutExpired:
                continue

        completed = subprocess.CompletedProcess(arguments, process.returncode, stdout[-_OUTPUT_LIMIT:], stderr[-_OUTPUT_LIMIT:])
        if completed.returncode != 0:
            raise AppError(
                code="ffmpeg_failed",
                user_message="视频处理失败。",
                technical_message=completed.stderr or f"Process exited with code {completed.returncode}",
                context=ErrorContext(stage=stage, log_excerpt=completed.stderr),
            )
        return completed

    def version(self) -> str:
        executable = self._require(self.ffmpeg_path, "FFmpeg")
        result = self._run([str(executable), "-version"], timeout=10, stage="Version check")
        return result.stdout.splitlines()[0] if result.stdout else "Unknown"

    def probe(self, media_path: str | Path, *, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        source = Path(media_path)
        if not source.is_file():
            raise ValueError(f"媒体文件不存在：{source}")
        executable = self._require(self.ffprobe_path, "ffprobe")
        result = self._run([
            str(executable), "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(source),
        ], cancel_event=cancel_event, timeout=30, stage="Probing media")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AppError(
                code="ffprobe_invalid_output",
                user_message="无法读取视频信息。",
                technical_message=result.stdout[-_OUTPUT_LIMIT:],
                context=ErrorContext(stage="Probing media"),
            ) from exc
        return payload

    def probe_duration(self, media_path: str | Path, *, cancel_event: threading.Event | None = None) -> float:
        payload = self.probe(media_path, cancel_event=cancel_event)
        try:
            duration = float(payload.get("format", {}).get("duration"))
        except (TypeError, ValueError) as exc:
            raise AppError(
                code="duration_unavailable",
                user_message="无法获取视频时长。",
                technical_message="ffprobe output did not contain a valid duration",
                context=ErrorContext(stage="Probing duration"),
            ) from exc
        return duration

    def has_audio_and_video(self, media_path: str | Path) -> bool:
        payload = self.probe(media_path)
        types = {stream.get("codec_type") for stream in payload.get("streams", [])}
        return {"audio", "video"}.issubset(types)

    def extract_frame(
        self,
        media_path: str | Path,
        timestamp: float,
        output_path: str | Path,
        *,
        duration: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        source = Path(media_path)
        if not source.is_file():
            raise ValueError(f"视频文件不存在：{source}")
        total = self.probe_duration(source, cancel_event=cancel_event) if duration is None else duration
        position = validate_timestamp(timestamp, total)
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp.jpg")
        executable = self._require(self.ffmpeg_path, "FFmpeg")
        try:
            self._run([
                str(executable), "-hide_banner", "-loglevel", "error",
                "-ss", f"{position:.3f}", "-i", str(source),
                "-frames:v", "1", "-q:v", "2", "-f", "image2", "-y", str(temporary),
            ], cancel_event=cancel_event, timeout=60, stage="Extracting thumbnail")
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise AppError(
                    code="thumbnail_empty",
                    user_message="无法生成该时间点的缩略图。",
                    technical_message="FFmpeg completed without creating an image",
                    context=ErrorContext(stage="Extracting thumbnail"),
                )
            os.replace(temporary, destination)
            return destination
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _stream_signature(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
        result: list[tuple[Any, ...]] = []
        for stream in payload.get("streams", []):
            if stream.get("disposition", {}).get("attached_pic"):
                continue
            tags = stream.get("tags") or {}
            result.append((
                stream.get("codec_type"),
                stream.get("codec_name"),
                stream.get("profile"),
                stream.get("width"),
                stream.get("height"),
                stream.get("sample_rate"),
                stream.get("channels"),
                stream.get("channel_layout"),
                tags.get("language"),
            ))
        return result

    @staticmethod
    def _chapter_signature(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [
            (
                chapter.get("start_time"),
                chapter.get("end_time"),
                tuple(sorted((chapter.get("tags") or {}).items())),
            )
            for chapter in payload.get("chapters", [])
        ]

    @staticmethod
    def _duration(payload: dict[str, Any]) -> float | None:
        try:
            return float(payload.get("format", {}).get("duration"))
        except (TypeError, ValueError):
            return None

    def _validate_cover_candidate(
        self,
        source_probe: dict[str, Any],
        candidate_probe: dict[str, Any],
    ) -> None:
        if self._stream_signature(source_probe) != self._stream_signature(candidate_probe):
            raise AppError(
                "cover_stream_mismatch",
                "封面写入验证失败，原视频未被替换。",
                "Primary stream codec/count/signature changed after cover mux",
                ErrorContext(stage="Validating embedded cover"),
            )
        covers = [
            stream for stream in candidate_probe.get("streams", [])
            if stream.get("disposition", {}).get("attached_pic")
        ]
        if len(covers) != 1 or covers[0].get("codec_name") not in {"mjpeg", "png"}:
            raise AppError(
                "cover_stream_missing",
                "视频容器没有正确保存唯一封面，原视频未被替换。",
                f"Expected one MJPEG/PNG attached_pic stream, found {len(covers)}",
                ErrorContext(stage="Validating embedded cover"),
            )
        source_duration = self._duration(source_probe)
        candidate_duration = self._duration(candidate_probe)
        if source_duration is not None and candidate_duration is not None:
            tolerance = max(0.25, source_duration * 0.01)
            if abs(source_duration - candidate_duration) > tolerance:
                raise AppError(
                    "cover_duration_mismatch",
                    "封面写入后视频时长异常，原视频未被替换。",
                    f"Duration changed from {source_duration} to {candidate_duration}",
                    ErrorContext(stage="Validating embedded cover"),
                )
        if self._chapter_signature(source_probe) != self._chapter_signature(candidate_probe):
            raise AppError(
                "cover_chapter_mismatch",
                "封面写入后章节信息异常，原视频未被替换。",
                "Chapter count, boundaries, or metadata changed",
                ErrorContext(stage="Validating embedded cover"),
            )
        source_tags = {
            key: value for key, value in (source_probe.get("format", {}).get("tags") or {}).items()
            if key.lower() not in _VOLATILE_FORMAT_TAGS
        }
        candidate_tags = candidate_probe.get("format", {}).get("tags") or {}
        changed = {
            key: (value, candidate_tags.get(key))
            for key, value in source_tags.items()
            if candidate_tags.get(key) != value
        }
        if changed:
            raise AppError(
                "cover_metadata_mismatch",
                "封面写入后关键元数据异常，原视频未被替换。",
                f"Metadata changed: {changed!r}",
                ErrorContext(stage="Validating embedded cover"),
            )

    def embed_cover(
        self,
        media_path: str | Path,
        cover_path: str | Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> CoverEmbedResult:
        source = Path(media_path)
        cover = Path(cover_path)
        if not source.is_file():
            raise ValueError(f"视频文件不存在：{source}")
        if not cover.is_file():
            raise ValueError(f"封面图片不存在：{cover}")
        if source.suffix.lower() not in _COVER_CONTAINERS:
            raise AppError(
                "cover_container_unsupported",
                "当前视频容器不支持无损写入 Explorer 封面；原视频没有改变。",
                f"Unsupported cover container: {source.suffix}",
                ErrorContext(stage="Embedding cover"),
            )
        source_probe = self.probe(source, cancel_event=cancel_event)
        source_streams = list(source_probe.get("streams", []))
        kept_stream_indexes = [
            int(stream["index"])
            for stream in source_streams
            if not stream.get("disposition", {}).get("attached_pic")
        ]
        cover_video_index = sum(
            stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")
            for stream in source_streams
        )
        candidate = source.with_name(
            f".{source.stem}.{uuid.uuid4().hex}.cover-candidate{source.suffix.lower()}"
        )
        executable = self._require(self.ffmpeg_path, "FFmpeg")
        mappings: list[str] = []
        for index in kept_stream_indexes:
            mappings.extend(("-map", f"0:{index}"))
        mappings.extend(("-map", "1:v:0"))
        try:
            self._run([
                str(executable), "-hide_banner", "-loglevel", "error",
                "-i", str(source), "-i", str(cover),
                *mappings,
                "-map_metadata", "0", "-map_chapters", "0",
                "-c", "copy",
                f"-disposition:v:{cover_video_index}", "attached_pic",
                f"-metadata:s:v:{cover_video_index}", "title=Cover",
                f"-metadata:s:v:{cover_video_index}", "comment=Cover (front)",
                "-movflags", "+faststart", "-y", str(candidate),
            ], cancel_event=cancel_event, timeout=300, stage="Embedding cover")
            candidate_probe = self.probe(candidate, cancel_event=cancel_event)
            self._validate_cover_candidate(source_probe, candidate_probe)

            explorer_status = ExplorerCoverStatus.UNAVAILABLE
            checker = self.shell_thumbnail_checker
            if checker is None and os.name == "nt":
                try:
                    from yt_downloader.infrastructure.windows_thumbnail import shell_thumbnail_matches
                    checker = shell_thumbnail_matches
                except Exception:
                    logger.exception("Windows Shell thumbnail checker is unavailable")
            if checker is not None:
                try:
                    matched = checker(candidate, cover)
                    explorer_status = (
                        ExplorerCoverStatus.MATCHED if matched is True
                        else ExplorerCoverStatus.NOT_USED if matched is False
                        else ExplorerCoverStatus.UNAVAILABLE
                    )
                except Exception:
                    logger.exception("Windows Shell cover verification failed")
                    explorer_status = ExplorerCoverStatus.UNAVAILABLE
            if cancel_event and cancel_event.is_set():
                raise OperationCancelled(ErrorContext(stage="Embedding cover"))
            os.replace(candidate, source)
            if os.name == "nt":
                try:
                    from yt_downloader.infrastructure.windows_thumbnail import notify_shell_updated
                    notify_shell_updated(source)
                except Exception:
                    logger.exception("Could not notify Windows Shell after cover update")
            if explorer_status is ExplorerCoverStatus.MATCHED:
                message = "封面已写入视频，Windows Explorer 已识别该封面。"
            elif explorer_status is ExplorerCoverStatus.NOT_USED:
                message = "封面已写入视频，但当前容器或系统的 Explorer 没有采用该封面。"
            else:
                message = "封面已写入视频，但无法在当前系统验证 Explorer 的显示结果。"
            return CoverEmbedResult(source, True, explorer_status, message)
        finally:
            candidate.unlink(missing_ok=True)

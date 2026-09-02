"""Safe, cancellable FFmpeg and ffprobe subprocess integration."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.infrastructure.runtime import find_tool


_OUTPUT_LIMIT = 64 * 1024


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
    ) -> None:
        self.ffmpeg_path = Path(ffmpeg_path) if ffmpeg_path else find_tool("ffmpeg", configured_directory)
        self.ffprobe_path = Path(ffprobe_path) if ffprobe_path else find_tool("ffprobe", configured_directory)

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
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
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


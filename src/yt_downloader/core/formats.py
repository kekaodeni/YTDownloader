"""Translate yt-dlp formats into stable, user-facing quality choices."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping

from .models import FormatOption


def _size(item: Mapping[str, Any]) -> int | None:
    value = item.get("filesize") or item.get("filesize_approx")
    return int(value) if isinstance(value, (int, float)) and value > 0 else None


def _codec_score(codec: str) -> int:
    value = codec.lower()
    if value.startswith(("avc1", "h264")):
        return 40
    if value.startswith(("vp9", "vp0")):
        return 30
    if value.startswith(("av01", "av1")):
        return 20
    return 10


def _video_score(item: Mapping[str, Any]) -> tuple[int, int, float]:
    ext = str(item.get("ext") or "")
    progressive = int(item.get("acodec") not in {None, "none"})
    return (
        _codec_score(str(item.get("vcodec") or "")) + (5 if ext == "mp4" else 0),
        progressive,
        float(item.get("tbr") or item.get("vbr") or 0),
    )


def _audio_score(item: Mapping[str, Any], video_ext: str) -> tuple[int, float]:
    ext = str(item.get("ext") or "")
    compatible = int((video_ext == "mp4" and ext in {"m4a", "mp4"}) or (video_ext == "webm" and ext == "webm"))
    return compatible, float(item.get("abr") or item.get("tbr") or 0)


def _quality_label(height: int, fps: float) -> str:
    suffix = " 4K" if height >= 2160 else " 2K" if height >= 1440 else ""
    fps_text = f" {round(fps):d} FPS" if fps >= 50 else ""
    return f"{height}p{suffix}{fps_text}"


def normalize_formats(raw_formats: Iterable[Mapping[str, Any]]) -> list[FormatOption]:
    formats = [dict(item) for item in raw_formats]
    videos = [
        item for item in formats
        if item.get("vcodec") not in {None, "none"} and isinstance(item.get("height"), (int, float))
    ]
    audios = [item for item in formats if item.get("vcodec") == "none" and item.get("acodec") not in {None, "none"}]

    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for item in videos:
        height = int(item["height"])
        if height < 144:
            continue
        fps = float(item.get("fps") or 0)
        fps_bucket = round(fps) if fps >= 50 else 30 if fps else 0
        grouped.setdefault((height, fps_bucket), []).append(item)

    options: list[FormatOption] = []
    for (height, _fps_bucket), candidates in grouped.items():
        video = max(candidates, key=_video_score)
        video_id = str(video.get("format_id") or "")
        if not video_id:
            continue
        video_ext = str(video.get("ext") or "mp4").lower()
        fps = float(video.get("fps") or 0)
        has_audio = video.get("acodec") not in {None, "none"}
        audio: dict[str, Any] | None = None
        if not has_audio and audios:
            audio = max(audios, key=lambda item: _audio_score(item, video_ext))

        audio_id = str(audio.get("format_id")) if audio else None
        selector = video_id if has_audio or not audio_id else f"{video_id}+{audio_id}"
        audio_ext = str(audio.get("ext") or "") if audio else video_ext
        if has_audio:
            final_ext = video_ext
        elif video_ext == "mp4" and audio_ext in {"m4a", "mp4"}:
            final_ext = "mp4"
        elif video_ext == "webm" and audio_ext == "webm":
            final_ext = "webm"
        else:
            final_ext = "mkv"

        video_size = _size(video)
        audio_size = _size(audio) if audio else None
        estimated = None
        if video_size is not None:
            estimated = video_size + (audio_size or 0)
        acodec = str(video.get("acodec") or (audio.get("acodec") if audio else "none") or "none")
        options.append(FormatOption(
            label=_quality_label(height, fps),
            height=height,
            fps=fps,
            vcodec=str(video.get("vcodec") or "unknown"),
            acodec=acodec,
            container=final_ext.upper() if final_ext != "webm" else "WebM",
            final_ext=final_ext,
            format_selector=selector,
            estimated_size=estimated,
            requires_merge=bool(audio_id),
            video_format_id=video_id,
            audio_format_id=audio_id,
        ))

    options.sort(key=lambda option: (option.height, option.fps), reverse=True)
    if options:
        compatible = [option for option in options if option.height <= 1080 and option.final_ext == "mp4"]
        recommended = max(compatible, key=lambda option: (option.height, -abs(option.fps - 30))) if compatible else options[0]
        options = [replace(option, is_recommended=option is recommended) for option in options]
    return options


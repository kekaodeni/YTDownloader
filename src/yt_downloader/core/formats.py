"""Translate yt-dlp formats into stable, user-facing quality choices."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping

from .models import FormatOption


def _size(item: Mapping[str, Any]) -> tuple[int | None, bool]:
    exact = item.get("filesize")
    if isinstance(exact, (int, float)) and exact > 0:
        return int(exact), False
    estimate = item.get("filesize_approx")
    if isinstance(estimate, (int, float)) and estimate > 0:
        return int(estimate), True
    return None, False


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


def _display_height(width: int | None, height: int | None) -> int | None:
    if height is None:
        return None
    if width is not None and height > width:
        return width
    return height


def _quality_label(width: int | None, height: int | None, fps: float | None) -> str:
    if height is None:
        return "未知清晰度"
    portrait = width is not None and height > width
    vertical_resolution = _display_height(width, height)
    assert vertical_resolution is not None
    suffix = " 4K" if vertical_resolution >= 2160 else " 2K" if vertical_resolution >= 1440 else ""
    fps_text = f" {round(fps):d} FPS" if fps is not None and fps >= 50 else ""
    orientation = " 竖屏" if portrait else ""
    return f"{vertical_resolution}p{suffix}{fps_text}{orientation}"


def normalize_formats(raw_formats: Iterable[Mapping[str, Any]]) -> list[FormatOption]:
    formats = [dict(item) for item in raw_formats]
    videos = [
        item for item in formats
        if item.get("vcodec") not in {None, "none"}
    ]
    audios = [item for item in formats if item.get("vcodec") == "none" and item.get("acodec") not in {None, "none"}]

    grouped: dict[tuple[int | None, int | None, int], list[dict[str, Any]]] = {}
    for item in videos:
        height = int(item["height"]) if isinstance(item.get("height"), (int, float)) else None
        width = int(item["width"]) if isinstance(item.get("width"), (int, float)) else None
        display_height = _display_height(width, height)
        if display_height is not None and display_height < 144:
            continue
        fps = float(item["fps"]) if isinstance(item.get("fps"), (int, float)) else None
        fps_bucket = round(fps) if fps is not None and fps >= 50 else 30 if fps else 0
        orientation_width = width if height is None or (width is not None and height > width) else None
        grouped.setdefault((height, orientation_width, fps_bucket), []).append(item)

    options: list[FormatOption] = []
    for (height, _orientation_width, _fps_bucket), candidates in grouped.items():
        video = max(candidates, key=_video_score)
        video_id = str(video.get("format_id") or "")
        if not video_id:
            continue
        video_ext = str(video.get("ext") or "mp4").lower()
        width = int(video["width"]) if isinstance(video.get("width"), (int, float)) else None
        fps = float(video["fps"]) if isinstance(video.get("fps"), (int, float)) else None
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

        video_size, video_size_is_estimate = _size(video)
        audio_size, audio_size_is_estimate = _size(audio) if audio else (None, False)
        if audio:
            estimated = video_size + audio_size if video_size is not None and audio_size is not None else None
            size_is_estimate = video_size_is_estimate or audio_size_is_estimate
        else:
            estimated = video_size
            size_is_estimate = video_size_is_estimate
        acodec = str(
            video.get("acodec") if has_audio
            else (audio.get("acodec") if audio else "none")
        )
        options.append(FormatOption(
            label=_quality_label(width, height, fps),
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
            width=width,
            size_is_estimate=size_is_estimate,
            video_size=video_size,
            video_size_is_estimate=video_size_is_estimate,
            audio_size=audio_size,
            audio_size_is_estimate=audio_size_is_estimate,
        ))

    options.sort(
        key=lambda option: (
            option.display_height is not None,
            option.display_height or 0,
            option.fps or 0,
        ),
        reverse=True,
    )
    if options:
        compatible = [
            option for option in options
            if option.display_height is not None
            and option.display_height <= 1080
            and option.final_ext == "mp4"
        ]
        recommended = max(
            compatible,
            key=lambda option: (option.display_height or 0, -abs((option.fps or 0) - 30)),
        ) if compatible else options[0]
        options = [replace(option, is_recommended=option is recommended) for option in options]
    return options

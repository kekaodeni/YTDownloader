"""Translate yt-dlp formats into stable, user-facing quality choices."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Iterable, Mapping

from .models import CodecFormatVariant, CodecPreference, FormatOption, SizeKind
from yt_downloader.services.format_resolver import YtDlpFormatResolver


@dataclass(frozen=True, slots=True)
class _BilibiliQualityTier:
    nominal_height: int
    rank: int
    label: str
    fps_mode: str = "none"


# These are Bilibili's user-facing DASH quality IDs. Keep them separate from
# the raw width/height/fps reported for each encoded candidate.
# HDR/Dolby Vision tiers retain their own quality identity, while their visible
# resolution comes from yt-dlp's actual dimensions rather than the quality ID.
_BILIBILI_QUALITY_TIERS: Mapping[int, _BilibiliQualityTier] = {
    6: _BilibiliQualityTier(240, 10, "240p"),
    16: _BilibiliQualityTier(360, 20, "360p"),
    32: _BilibiliQualityTier(480, 30, "480p"),
    64: _BilibiliQualityTier(720, 40, "720p"),
    74: _BilibiliQualityTier(720, 50, "720p 60 FPS", "fixed60"),
    80: _BilibiliQualityTier(1080, 60, "1080p"),
    112: _BilibiliQualityTier(1080, 70, "1080p 高码率"),
    116: _BilibiliQualityTier(1080, 80, "1080p 60 FPS", "fixed60"),
    120: _BilibiliQualityTier(2160, 90, "2160p 4K", "measured"),
    122: _BilibiliQualityTier(2160, 95, "2160p 4K SDR增强", "measured"),
    125: _BilibiliQualityTier(0, 100, "", "measured"),
    126: _BilibiliQualityTier(0, 110, "", "measured"),
}


def bilibili_quality_rank(quality):
    """Share the semantic tier ordering with deferred per-episode fallback."""
    tier = _BILIBILI_QUALITY_TIERS.get(quality)
    return tier.rank if tier else None


def semantic_quality_target(option):
    """A known Bilibili tier is stable across episodes, unlike format IDs."""
    return f'bilibili:{option.site_quality}' if option.quality_rank is not None else option.label


def _size(
    item: Mapping[str, Any],
    _duration: float | None = None,
) -> tuple[int | None, bool]:
    exact = item.get("filesize")
    if isinstance(exact, (int, float)) and exact > 0:
        return int(exact), False
    estimate = item.get("filesize_approx")
    if isinstance(estimate, (int, float)) and estimate > 0:
        return int(estimate), True
    return None, False


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


def _youtube_semantic_quality(item: Mapping[str, Any]) -> tuple[int | None, float | None, str]:
    """Read YouTube's qualityLabel exposed by yt-dlp; never infer it from itags.

    Numeric `quality` is an extractor ranking, and `resolution` is physical.
    The synthesized `format` can retain the note in parentheses when the note
    itself is absent. Ambiguous/missing labels retain the physical fallback.
    """
    for field, text in (("format-note", str(item.get("format_note") or "")),
                        ("format", " ".join(re.findall(r"\(([^()]*)\)", str(item.get("format") or ""))))):
        matches = {(int(height), float(fps) if fps else None)
                   for height, fps in re.findall(r"(?<![\w.])(\d{3,4})p(\d{2,3})?(?!\w)", text, re.I)
                   if 144 <= int(height) <= 8640 and (not fps or 1 < int(fps) <= 240)}
        if len(matches) == 1:
            height, fps = matches.pop()
            return height, fps, f"youtube-{field}"
    return None, None, "raw-dimensions"


def _youtube_range_label(item: Mapping[str, Any]) -> str:
    value = str(item.get("dynamic_range") or "").casefold()
    return {"sdr": "", "": "", "hdr": "HDR", "hdr10": "HDR",
            "hdr10+": "HDR10+", "hlg": "HLG", "dv": "杜比视界"}.get(value, value.upper())


def _youtube_preferred_renditions(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer the highest FPS family; let yt-dlp order codecs within it.

    Keep all candidates on the option, including lower-FPS fallbacks. Nearby
    measured rates (29.97/30, 59.94/60) belong to the same rendition family.
    """
    def fps_rank(item: Mapping[str, Any]) -> int:
        _, semantic_fps, _ = _youtube_semantic_quality(item)
        fps = semantic_fps or item.get("fps")
        return round(fps) if isinstance(fps, (int, float)) else 0

    highest = max(map(fps_rank, candidates))
    return [item for item in candidates if fps_rank(item) == highest]


def _option_for_selection(
    resolved, candidates, duration, quality_tier=None, orientation=None, site_quality=None,
    youtube=False,
):
    video = dict(resolved.video)
    video_id = str(video.get("format_id") or "")
    if not video_id:
        return None
    video_ext = str(video.get("ext") or "mp4").lower()
    width = int(video["width"]) if isinstance(video.get("width"), (int, float)) else None
    fps = float(video["fps"]) if isinstance(video.get("fps"), (int, float)) else None
    detected = video.get("_display_probe") or {}
    detected_width = int(detected["width"]) if isinstance(detected.get("width"), (int, float)) else None
    detected_height = int(detected["height"]) if isinstance(detected.get("height"), (int, float)) else None
    detected_fps = float(detected["fps"]) if isinstance(detected.get("fps"), (int, float)) else None
    has_audio = video.get("acodec") not in {None, "none"}
    audio = dict(resolved.audio) if resolved.audio else None
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
    video_size, video_size_is_estimate = _size(video, duration)
    audio_size, audio_size_is_estimate = _size(audio, duration) if audio else (None, False)
    if audio:
        estimated = video_size + audio_size if video_size is not None and audio_size is not None else None
        size_is_estimate = video_size_is_estimate or audio_size_is_estimate
    else:
        estimated = video_size
        size_is_estimate = video_size_is_estimate
    acodec = str(
        video.get("acodec") if has_audio
        else (audio.get("acodec") or "unknown" if audio
              else "unknown" if video.get("acodec") is None
              else "none")
    )
    height = int(video["height"]) if isinstance(video.get("height"), (int, float)) else None
    display_width = width if width is not None else detected_width
    display_raw_height = height if height is not None else detected_height
    is_portrait = (display_raw_height is not None and display_width is not None and display_raw_height > display_width
                   if orientation is None else orientation)
    semantic_fps = None
    youtube_height, youtube_fps, youtube_source = (_youtube_semantic_quality(video) if youtube
                                                  else (None, None, ""))
    if quality_tier and quality_tier.fps_mode == "fixed60":
        semantic_fps = 60.0
    elif quality_tier and quality_tier.fps_mode == "measured" and fps is not None and fps >= 50:
        semantic_fps = 60.0
    if quality_tier:
        dynamic_range = str(video.get("dynamic_range") or "")
        semantic_range_tier = site_quality in {125, 126}
        if semantic_range_tier:
            range_value = dynamic_range.casefold()
            label = ("杜比视界" if range_value == "dv" or site_quality == 126
                     else "HDR" if range_value in {"hdr", "hdr10"} or site_quality == 125
                     else quality_tier.label or "原始画质")
        else:
            label = quality_tier.label or _quality_label(width, height, None)
            if label == "未知清晰度":
                label = "原始画质"
        if not semantic_range_tier and dynamic_range.casefold() == "dv":
            label += " 杜比视界"
        elif not semantic_range_tier and dynamic_range.casefold() in {"hdr", "hdr10"}:
            label += " HDR"
        elif not semantic_range_tier and dynamic_range and dynamic_range.casefold() != "sdr":
            label += f" {dynamic_range}"
        if quality_tier.fps_mode == "measured" and semantic_fps:
            label += " 60 FPS"
        if is_portrait:
            label += " 竖屏"
    elif youtube_height is not None:
        effective_fps = youtube_fps or fps
        semantic_fps = 60.0 if effective_fps is not None and effective_fps >= 50 else None
        label = _quality_label(None, youtube_height, semantic_fps)
        if range_label := _youtube_range_label(video):
            label += f" {range_label}"
        if is_portrait:
            label += " 竖屏"
    else:
        label = _quality_label(width or detected_width, height or detected_height, fps or detected_fps)
        if label == "未知清晰度" and detected.get("source") == "original":
            label = "原始画质"
        if youtube and (range_label := _youtube_range_label(video)):
            label += f" {range_label}"
    return FormatOption(
        label=label,
        height=height, fps=fps, vcodec=str(video.get("vcodec") or "unknown"), acodec=acodec,
        container=final_ext.upper() if final_ext != "webm" else "WebM", final_ext=final_ext,
        format_selector=selector, estimated_size=estimated, requires_merge=bool(audio_id),
        video_format_id=video_id, audio_format_id=audio_id, video_extension=video_ext,
        audio_extension=audio_ext, candidate_video_format_ids=tuple(
            str(item["format_id"]) for item in candidates if item.get("format_id")),
        width=width, size_is_estimate=size_is_estimate, video_size=video_size,
        video_size_is_estimate=video_size_is_estimate, audio_size=audio_size,
        audio_size_is_estimate=audio_size_is_estimate, video_protocol=str(video.get("protocol") or ""),
        audio_protocol=str(audio.get("protocol") or "") if audio else "",
        site_quality=site_quality,
        semantic_height=(quality_tier.nominal_height or None) if quality_tier else youtube_height,
        semantic_fps=semantic_fps,
        quality_rank=quality_tier.rank if quality_tier else None,
        semantic_portrait=is_portrait if quality_tier else None,
        dynamic_range=str(video.get("dynamic_range") or ""),
        detected_width=detected_width, detected_height=detected_height, detected_fps=detected_fps,
        display_metadata_source=str(detected.get("source") or "yt-dlp"),
        semantic_quality_source=("bilibili-qn" if quality_tier else youtube_source if youtube_height
                                 else str(detected.get("source") or "raw-dimensions")),
        size_kind=(SizeKind.UNKNOWN if estimated is None else SizeKind.ESTIMATED
                   if size_is_estimate else SizeKind.EXACT),
    )


def apply_codec_preference(option: FormatOption, preference: CodecPreference) -> FormatOption:
    """Apply a task's codec choice after complete metadata normalization."""
    if preference is CodecPreference.AUTO or not option.codec_variants:
        return option
    variant = next((item for item in option.codec_variants
                    if item.codec_preference is preference), None)
    if variant is None:
        return option
    return replace(option, video_format_id=variant.video_format_id,
                   audio_format_id=variant.audio_format_id, format_selector=variant.format_selector,
                   vcodec=variant.vcodec, acodec=variant.acodec, container=variant.container,
                   final_ext=variant.final_ext, estimated_size=variant.estimated_size,
                   requires_merge=variant.requires_merge, width=variant.width, height=variant.height,
                   fps=variant.fps,
                   video_size=variant.video_size, video_size_is_estimate=variant.video_size_is_estimate,
                   audio_size=variant.audio_size, audio_size_is_estimate=variant.audio_size_is_estimate,
                   video_protocol=variant.video_protocol, audio_protocol=variant.audio_protocol,
                   video_extension=variant.video_extension, audio_extension=variant.audio_extension,
                   size_kind=variant.size_kind, dynamic_range=variant.dynamic_range)


def normalize_formats(
    raw_formats: Iterable[Mapping[str, Any]],
    *,
    duration: float | None = None,
    resolver: YtDlpFormatResolver | None = None,
    extractor_key: str = "",
) -> list[FormatOption]:
    formats = [dict(item) for item in raw_formats]
    videos = [
        item for item in formats
        # Some native HLS extractors (including HuyaVideo) return a usable
        # resolution and URL while leaving both codec fields unknown. Keep
        # those candidates so yt-dlp can choose them; audio-only renditions
        # have vcodec='none' and remain excluded here.
        if item.get("vcodec") != "none"
        and (item.get("vcodec") is not None or isinstance(item.get("height"), (int, float))
             or (len(formats) == 1 and item.get("format_id")
                 and (item.get("url") or item.get("protocol"))
                 and item.get("acodec") is None))
    ]
    # Some extractors (including X HLS) identify an audio rendition with
    # vcodec=none but leave acodec unknown. yt-dlp can still select it.
    audios = [item for item in formats if item.get("vcodec") == "none" and item.get("acodec") != "none"]

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for item in videos:
        height = int(item["height"]) if isinstance(item.get("height"), (int, float)) else None
        width = int(item["width"]) if isinstance(item.get("width"), (int, float)) else None
        display_height = _display_height(width, height)
        fps = float(item["fps"]) if isinstance(item.get("fps"), (int, float)) else None
        # Low frame rate and unspecified FPS share the same visible tier because
        # neither produces a frame-rate suffix in the UI.
        fps_bucket = (0 if height is None else round(fps) if fps is not None and fps >= 50 else 30)
        is_bilibili = extractor_key.casefold().startswith("bilibili")
        raw_site_quality = (int(item["quality"])
                            if is_bilibili
                            and isinstance(item.get("quality"), (int, float)) else None)
        quality_tier = _BILIBILI_QUALITY_TIERS.get(raw_site_quality)
        if quality_tier:
            portrait = width is not None and height is not None and height > width
            dynamic_range = str(item.get("dynamic_range") or "")
            semantic_fps = (60 if quality_tier.fps_mode == "fixed60"
                            or quality_tier.fps_mode == "measured" and fps is not None and fps >= 50
                            else 0)
            key = ("bilibili", raw_site_quality, dynamic_range, semantic_fps, portrait)
        elif extractor_key.casefold() == "youtube":
            semantic_height, semantic_fps, _ = _youtube_semantic_quality(item)
            if semantic_height is None and display_height is not None and display_height < 144:
                continue
            effective_fps = semantic_fps or fps
            # A semantic tier is one user choice, not one choice per FPS.
            # Unlabelled formats retain the existing physical/FPS fallback.
            bucket = (None if semantic_height is not None else
                      round(effective_fps) if effective_fps is not None and effective_fps >= 50 else 30)
            portrait = width is not None and height is not None and height > width
            key = ("youtube", semantic_height or display_height, bucket,
                   _youtube_range_label(item), portrait)
        else:
            if display_height is not None and display_height < 144:
                continue
            orientation_width = width if height is None or (width is not None and height > width) else None
            key = ("generic", height, orientation_width, fps_bucket,
                   raw_site_quality if is_bilibili else None)
        grouped.setdefault(key, []).append(item)

    options: list[FormatOption] = []
    resolver = resolver or YtDlpFormatResolver()
    for group_key, candidates in grouped.items():
        if group_key[0] == "bilibili":
            site_quality = group_key[1]
            quality_tier = _BILIBILI_QUALITY_TIERS[site_quality]
            orientation = group_key[4]
        elif group_key[0] == "youtube":
            site_quality = quality_tier = orientation = None
        else:
            site_quality = group_key[4]
            quality_tier = None
            orientation = None
        preferred = (_youtube_preferred_renditions(candidates)
                     if group_key[0] == "youtube" and group_key[2] is None else candidates)
        resolved = resolver.resolve(preferred, audios, CodecPreference.AUTO)
        if resolved is None:
            continue
        option = _option_for_selection(resolved, candidates, duration, quality_tier, orientation, site_quality,
                                       youtube=group_key[0] == "youtube")
        if option is None:
            continue
        variants = []
        for preference in (CodecPreference.AV1, CodecPreference.VP9, CodecPreference.H264):
            alternate = resolver.resolve(preferred, audios, preference)
            alternate_option = (_option_for_selection(
                alternate, candidates, duration, quality_tier, orientation, site_quality,
                youtube=group_key[0] == "youtube",
            ) if alternate else None)
            if alternate_option is None or alternate_option.video_format_id == option.video_format_id:
                continue
            variants.append(CodecFormatVariant(
                codec_preference=preference, video_format_id=alternate_option.video_format_id,
                audio_format_id=alternate_option.audio_format_id, format_selector=alternate_option.format_selector,
                vcodec=alternate_option.vcodec, acodec=alternate_option.acodec,
                container=alternate_option.container, final_ext=alternate_option.final_ext,
                estimated_size=alternate_option.estimated_size, requires_merge=alternate_option.requires_merge,
                width=alternate_option.width, height=alternate_option.height, fps=alternate_option.fps,
                video_size=alternate_option.video_size,
                video_size_is_estimate=alternate_option.video_size_is_estimate,
                audio_size=alternate_option.audio_size, audio_size_is_estimate=alternate_option.audio_size_is_estimate,
                video_protocol=alternate_option.video_protocol, audio_protocol=alternate_option.audio_protocol,
                video_extension=alternate_option.video_extension, audio_extension=alternate_option.audio_extension,
                size_kind=alternate_option.size_kind, dynamic_range=alternate_option.dynamic_range))
        options.append(replace(option, codec_variants=tuple(variants)))

    label_counts: dict[str, int] = {}
    for option in options:
        label_counts[option.label] = label_counts.get(option.label, 0) + 1
    options = [
        replace(option, label=f"{option.label} (QN {option.site_quality})")
        if label_counts[option.label] > 1 and option.site_quality is not None and option.quality_rank is None
        else option
        for option in options
    ]
    options.sort(key=lambda option: option.quality_sort_key, reverse=True)
    if options:
        compatible = [
            option for option in options
            if option.display_height is not None
            and option.display_height <= 1080
        ]
        recommended = max(
            compatible,
            key=lambda option: (option.display_height or 0, option.quality_rank or 0,
                                -abs((option.display_fps or 0) - 30)),
        ) if compatible else options[0]
        options = [replace(option, is_recommended=option is recommended) for option in options]
    return options


def normalize_audio_formats(raw_formats):
    options = []
    for item in sorted(raw_formats, key=lambda value: float(value.get('abr') or value.get('tbr') or 0), reverse=True):
        if item.get('vcodec') != 'none' or item.get('acodec') == 'none' or not item.get('format_id'):
            continue
        ext = str(item.get('ext') or 'm4a')
        size, estimate = _size(item)
        bitrate = item.get('abr')
        label = ext.upper() + (f' · {round(bitrate)} kbps' if isinstance(bitrate, (int, float)) else ' · Original')
        options.append(FormatOption(label, None, None, 'none', str(item.get('acodec') or 'unknown'), ext.upper(),
                                    ext, str(item['format_id']), size, False, str(item['format_id']),
                                    audio_extension=ext, video_size=size, audio_size=size,
                                    size_is_estimate=estimate, video_protocol=str(item.get('protocol') or '')))
    return options

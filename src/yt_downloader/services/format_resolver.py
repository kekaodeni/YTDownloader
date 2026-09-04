"""Version-isolated adapter around yt-dlp's own format selection engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

import yt_dlp

from yt_downloader.core.models import CodecPreference


@dataclass(frozen=True, slots=True)
class ResolvedFormatSelection:
    video: Mapping[str, Any]
    audio: Mapping[str, Any] | None

    @property
    def selector(self) -> str:
        video_id = str(self.video.get("format_id") or "")
        audio_id = str(self.audio.get("format_id") or "") if self.audio else ""
        return f"{video_id}+{audio_id}" if audio_id else video_id


class YtDlpFormatResolver:
    """Delegate ordering to the bundled yt-dlp instead of duplicating it."""

    def __init__(
        self,
        ydl_factory: Callable[[dict[str, Any]], Any] = yt_dlp.YoutubeDL,
    ) -> None:
        self.ydl_factory = ydl_factory

    @staticmethod
    def _matches_codec(item: Mapping[str, Any], preference: CodecPreference) -> bool:
        codec = str(item.get("vcodec") or "").lower()
        if preference is CodecPreference.AUTO:
            return True
        if preference is CodecPreference.AV1:
            return codec.startswith(("av01", "av1"))
        if preference is CodecPreference.VP9:
            return codec.startswith(("vp09", "vp9", "vp0"))
        return codec.startswith(("avc1", "h264"))

    def resolve(
        self,
        video_candidates: Iterable[Mapping[str, Any]],
        audio_candidates: Iterable[Mapping[str, Any]],
        preference: CodecPreference,
    ) -> ResolvedFormatSelection | None:
        videos = [
            self._sortable_copy(item)
            for item in video_candidates
            if self._matches_codec(item, preference)
        ]
        if not videos:
            return None
        formats = [*(self._sortable_copy(item) for item in audio_candidates), *videos]
        with self.ydl_factory({"quiet": True, "no_warnings": True}) as ydl:
            ydl.sort_formats({"formats": formats})
            selector = ydl.build_format_selector(
                "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            )
            selected = ydl._select_formats(formats, selector)
        if not selected:
            return None
        result = selected[-1]
        requested = list(result.get("requested_formats") or [result])
        video = next(
            (item for item in requested if item.get("vcodec") not in {None, "none"}),
            None,
        )
        if video is None:
            return None
        audio = next(
            (
                item for item in requested
                if item is not video
                and item.get("vcodec") == "none"
                and item.get("acodec") not in {None, "none"}
            ),
            None,
        )
        return ResolvedFormatSelection(video, audio)

    @staticmethod
    def _sortable_copy(item: Mapping[str, Any]) -> dict[str, Any]:
        copied = dict(item)
        # Real extractor formats always carry a URL or protocol.  Small,
        # redacted contract fixtures intentionally omit signed URLs; a neutral
        # protocol lets yt-dlp exercise the same ordering without inventing a
        # network endpoint.
        if not copied.get("protocol") and not copied.get("url"):
            copied["protocol"] = "https"
        return copied

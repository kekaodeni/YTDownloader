"""Stable aggregation for yt-dlp component progress."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from yt_downloader.core.models import FormatOption, ProgressTotalSource


@dataclass(frozen=True, slots=True)
class AggregateProgressSnapshot:
    downloaded_bytes: int | None
    total_bytes: int | None
    total_is_estimate: bool
    total_source: ProgressTotalSource


class AggregateProgressTracker:
    """Lock exact totals, but keep yt-dlp estimates live and explicitly labeled."""

    def __init__(self, option: FormatOption) -> None:
        expected = [option.video_format_id]
        if option.audio_format_id:
            expected.append(option.audio_format_id)
        self.expected_format_ids = frozenset(expected)
        self._component_downloaded: dict[str, int] = {}
        self._component_totals: dict[str, int] = {}
        self._component_estimates: dict[str, bool] = {}
        self._component_sources: dict[str, ProgressTotalSource] = {}
        self._last_downloaded: int | None = None
        self._locked_total = (
            option.estimated_size
            if option.estimated_size is not None and not option.size_is_estimate
            else None
        )
        self._locked_is_estimate = False
        self._locked_source = (
            ProgressTotalSource.METADATA_FILESIZE
            if self._locked_total is not None
            else ProgressTotalSource.UNKNOWN
        )
        self._add_hint(
            option.video_format_id,
            option.video_size,
            option.video_size_is_estimate,
        )
        if option.audio_format_id:
            self._add_hint(
                option.audio_format_id,
                option.audio_size,
                option.audio_size_is_estimate,
            )
        self._try_lock_total()

    def _add_hint(self, format_id: str, size: int | None, is_estimate: bool) -> None:
        if size is None or size <= 0:
            return
        self._component_totals[format_id] = size
        self._component_estimates[format_id] = is_estimate
        self._component_sources[format_id] = (
            ProgressTotalSource.METADATA_FILESIZE_APPROX
            if is_estimate else ProgressTotalSource.METADATA_FILESIZE
        )

    def _format_id(self, data: Mapping[str, Any]) -> str:
        info = data.get("info_dict") or {}
        format_id = str(info.get("format_id") or "")
        if not format_id and len(self.expected_format_ids) == 1:
            return next(iter(self.expected_format_ids))
        return format_id

    def _try_lock_total(self) -> None:
        if self._locked_total is not None:
            return
        if not self.expected_format_ids.issubset(self._component_totals):
            return
        if any(self._component_estimates[key] for key in self.expected_format_ids):
            return
        self._locked_total = sum(
            self._component_totals[format_id]
            for format_id in self.expected_format_ids
        )
        self._locked_is_estimate = any(
            self._component_estimates[format_id]
            for format_id in self.expected_format_ids
        )
        sources = {
            self._component_sources[format_id]
            for format_id in self.expected_format_ids
        }
        self._locked_source = (
            sources.pop()
            if len(sources) == 1
            else ProgressTotalSource.MIXED
        )

    def update(
        self,
        data: Mapping[str, Any],
        *,
        finished: bool = False,
    ) -> AggregateProgressSnapshot:
        format_id = self._format_id(data)
        if format_id in self.expected_format_ids:
            downloaded = data.get("downloaded_bytes")
            if isinstance(downloaded, (int, float)) and downloaded >= 0:
                self._component_downloaded[format_id] = max(
                    self._component_downloaded.get(format_id, 0),
                    int(downloaded),
                )
            total = data.get("total_bytes")
            estimate = data.get("total_bytes_estimate")
            if isinstance(total, (int, float)) and total > 0:
                self._component_totals[format_id] = int(total)
                self._component_estimates[format_id] = False
                self._component_sources[format_id] = ProgressTotalSource.HOOK_TOTAL_BYTES
            elif (
                isinstance(estimate, (int, float)) and estimate > 0
                and data.get("fragment_index") != 0
                and self._component_estimates.get(format_id, True)
            ):
                # Native HLS/DASH estimates evolve as fragments arrive. Never
                # freeze an initialization fragment's tiny size as the total.
                self._component_totals[format_id] = int(estimate)
                self._component_estimates[format_id] = True
                self._component_sources[format_id] = ProgressTotalSource.HOOK_TOTAL_BYTES_ESTIMATE
            if finished:
                final_downloaded = self._component_downloaded.get(format_id, 0)
                if final_downloaded > 0 and (
                    format_id not in self._component_totals
                    or self._component_estimates.get(format_id, True)
                ):
                    self._component_totals[format_id] = final_downloaded
                    self._component_estimates[format_id] = False
                    self._component_sources[format_id] = ProgressTotalSource.HOOK_TOTAL_BYTES
                if format_id in self._component_totals:
                    self._component_downloaded[format_id] = max(
                        final_downloaded,
                        self._component_totals[format_id],
                    )

        aggregate = (
            sum(self._component_downloaded.values())
            if self._component_downloaded
            else None
        )
        if aggregate is not None:
            self._last_downloaded = max(self._last_downloaded or 0, aggregate)
        self._try_lock_total()
        return self.snapshot()

    def snapshot(self) -> AggregateProgressSnapshot:
        if self._locked_total is None and self.expected_format_ids.issubset(self._component_totals):
            sources = {self._component_sources[key] for key in self.expected_format_ids}
            return AggregateProgressSnapshot(
                self._last_downloaded,
                sum(self._component_totals[key] for key in self.expected_format_ids),
                True,
                sources.pop() if len(sources) == 1 else ProgressTotalSource.MIXED,
            )
        return AggregateProgressSnapshot(
            self._last_downloaded,
            self._locked_total,
            self._locked_is_estimate,
            self._locked_source,
        )

    def terminal_stage_snapshot(self) -> AggregateProgressSnapshot:
        current = self.snapshot()
        if current.total_bytes is None:
            return current
        return AggregateProgressSnapshot(
            current.total_bytes,
            current.total_bytes,
            current.total_is_estimate,
            current.total_source,
        )

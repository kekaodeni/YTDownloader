"""Validation and time parsing for yt-dlp's native download sections."""

from __future__ import annotations

import re
from math import isfinite


_CLOCK = re.compile(r'^\d+(?::\d{1,2}){1,2}$')


def parse_clip_time(value: str) -> int:
    """Parse MM:SS or HH:MM:SS into whole seconds."""
    value = str(value or '').strip()
    if not _CLOCK.fullmatch(value):
        raise ValueError('Enter time as MM:SS or HH:MM:SS.')
    parts = [int(part) for part in value.split(':')]
    if any(part < 0 for part in parts) or parts[-1] >= 60 or (len(parts) == 3 and parts[-2] >= 60):
        raise ValueError('Seconds and minutes must be below 60.')
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def validate_clip(enabled: bool, start: int, end: int, duration: float | None) -> None:
    if not enabled:
        return
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise ValueError('The clip end time must be later than its start time.')
    if duration is not None and isfinite(duration) and end > duration:
        raise ValueError('The clip end time cannot exceed the video duration.')

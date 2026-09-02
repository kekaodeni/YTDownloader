"""Honest human-readable formatting for sizes and progress."""

from __future__ import annotations


def format_bytes(value: int | float | None) -> str:
    if value is None or value < 0:
        return "—"
    amount = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while amount >= 1024 and unit_index < len(units) - 1:
        amount /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(amount)} B"
    return f"{amount:.1f} {units[unit_index]}"


def format_speed(value: int | float | None) -> str:
    text = format_bytes(value)
    return text if text == "—" else f"{text}/s"


def _format_seconds(value: int | float | None) -> str:
    if value is None or value < 0:
        return "—"
    seconds = int(round(value))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def format_eta(value: int | float | None) -> str:
    return _format_seconds(value)


def format_duration(value: int | float | None) -> str:
    return _format_seconds(value)


def calculate_percent(
    downloaded_bytes: int | float | None,
    total_bytes: int | float | None,
    total_bytes_estimate: int | float | None,
) -> float | None:
    if downloaded_bytes is None:
        return None
    total = total_bytes or total_bytes_estimate
    if total is None or total <= 0:
        return None
    return max(0.0, min(100.0, float(downloaded_bytes) * 100.0 / float(total)))


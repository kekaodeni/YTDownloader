from yt_downloader.core.formatting import (
    calculate_percent,
    format_bytes,
    format_duration,
    format_eta,
    format_speed,
)


def test_formats_sizes_speeds_and_time_without_fake_values() -> None:
    assert format_bytes(None) == "—"
    assert format_bytes(0) == "0 B"
    assert format_bytes(1536) == "1.5 KB"
    assert format_bytes(1024**3) == "1.0 GB"
    assert format_speed(None) == "—"
    assert format_speed(8.4 * 1024**2) == "8.4 MB/s"
    assert format_eta(None) == "—"
    assert format_eta(48) == "00:48"
    assert format_duration(12 * 60 + 46) == "12:46"


def test_calculates_progress_from_real_or_estimated_total() -> None:
    assert calculate_percent(50, 100, None) == 50.0
    assert calculate_percent(25, None, 100) == 25.0
    assert calculate_percent(150, 100, None) == 100.0
    assert calculate_percent(20, None, None) is None

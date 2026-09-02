from pathlib import Path

from yt_downloader.core.filename import ensure_unique_path, sanitize_filename


def test_sanitizes_windows_names_without_losing_unicode() -> None:
    assert sanitize_filename('  中文😀: A/B*?"<>|.  ') == "中文😀_ A_B______"
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("...   ") == "YouTube 视频"


def test_limits_full_path_and_resolves_collisions(tmp_path: Path) -> None:
    long_name = "长" * 400
    safe = sanitize_filename(long_name, directory=tmp_path, extension=".mp4")
    assert len(str(tmp_path / f"{safe}.mp4").encode("utf-16-le")) // 2 <= 240

    existing = tmp_path / "视频.mp4"
    existing.touch()
    assert ensure_unique_path(existing).name == "视频 (1).mp4"

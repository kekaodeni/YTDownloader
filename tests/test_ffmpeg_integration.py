from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.ffmpeg_service import FfmpegService


@pytest.mark.integration
def test_real_ffmpeg_probe_unicode_path_and_frame_extraction(tmp_path: Path) -> None:
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg integration tools are unavailable")
    chinese = tmp_path / "中文 视频"
    chinese.mkdir()
    media = chinese / "含音频.mp4"
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x0067c0:s=320x180:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-y", str(media),
    ], shell=False, check=True, capture_output=True)
    service = FfmpegService(ffmpeg, ffprobe)

    assert 1.8 <= service.probe_duration(media) <= 2.2
    assert service.has_audio_and_video(media)
    thumbnail = service.extract_frame(media, 1.0, chinese / "缩略图.jpg", duration=2.0)
    assert thumbnail.is_file()
    assert thumbnail.stat().st_size > 0


"""Offline checks executed inside the packaged process."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import yt_dlp_ejs

from yt_downloader.core.formats import normalize_formats
from yt_downloader.infrastructure.runtime import resource_path
from yt_downloader.services.ffmpeg_service import FfmpegService


def run_packaged_self_test(*, cache_directory: Path, ffmpeg: FfmpegService, deno_path: Path | None) -> Path:
    icon = resource_path("assets", "app.ico")
    if not icon.is_file():
        raise RuntimeError("Application icon resource is missing")
    if not deno_path or not deno_path.is_file():
        raise RuntimeError("Bundled Deno is missing")
    if not ffmpeg.available:
        raise RuntimeError("Bundled FFmpeg/ffprobe is missing")
    options = normalize_formats([
        {"format_id": "18", "ext": "mp4", "height": 360, "fps": 30, "vcodec": "avc1", "acodec": "mp4a", "filesize": 1},
    ])
    if not options or options[0].label != "360p":
        raise RuntimeError("Metadata normalization self-test failed")

    cache_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-self-test-", dir=cache_directory) as temporary:
        media = Path(temporary) / "自检.mp4"
        ffmpeg._run([
            str(ffmpeg.ffmpeg_path), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=0x0067c0:s=160x90:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-y", str(media),
        ], timeout=30, stage="Packaged FFmpeg self-test")
        if not ffmpeg.has_audio_and_video(media):
            raise RuntimeError("Packaged FFmpeg stream validation failed")
    report = cache_directory / "package-self-test.json"
    report.write_text(json.dumps({
        "status": "ok",
        "deno": str(deno_path),
        "ffmpeg": str(ffmpeg.ffmpeg_path),
        "yt_dlp_ejs": str(Path(yt_dlp_ejs.__file__).name),
        "metadata_mock": "ok",
        "ffmpeg_audio_video": "ok",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


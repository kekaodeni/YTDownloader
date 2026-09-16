"""Opt-in live smoke test; excluded from pytest because it requires YouTube."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import uuid

from yt_downloader.core.models import DownloadRequest
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.youtube_service import YoutubeService


def run_smoke(work: Path) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://www.youtube.com/watch?v=jNQXAC9IVRw")
    parser.add_argument("--output", type=Path, default=work / "download")
    args = parser.parse_args()
    deno = find_tool("deno")
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    if not deno or not ffmpeg or not ffprobe:
        raise SystemExit("Run scripts/prepare_tools.ps1 first; locked Deno/FFmpeg tools are required.")
    cancel = threading.Event()
    video = YoutubeService(deno_path=deno).fetch_metadata(args.url, cancel)
    option = video.formats[-1]
    args.output.mkdir(parents=True, exist_ok=True)
    request = DownloadRequest(uuid.uuid4().hex, video, option, args.output, "YTDownloader smoke")
    result = DownloadService(deno_path=deno, ffmpeg_path=ffmpeg).download(
        request,
        lambda progress: print(progress.status.value, progress.percent, progress.speed),
        cancel,
    )
    if not FfmpegService(ffmpeg, ffprobe).has_audio_and_video(result.file_path):
        raise SystemExit("Smoke output does not contain both audio and video streams.")
    print(result.file_path)
    return 0


def main() -> int:
    from dev_staging import session
    with session('live-smoke') as work:
        return run_smoke(work)


if __name__ == "__main__":
    raise SystemExit(main())

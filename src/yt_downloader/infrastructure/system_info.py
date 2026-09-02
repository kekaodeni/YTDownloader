from __future__ import annotations

import platform
import sys
from pathlib import Path

import PySide6
import yt_dlp.version

from yt_downloader import __version__


def build_system_info(*, ffmpeg_path: Path | None, deno_path: Path | None, data_path: Path) -> str:
    return "\n".join((
        f"YT Downloader: {__version__}",
        f"Windows: {platform.platform()}",
        f"Python: {sys.version.split()[0]}",
        f"PySide6: {PySide6.__version__}",
        f"yt-dlp: {yt_dlp.version.__version__}",
        f"FFmpeg: {ffmpeg_path or '未找到'}",
        f"Deno: {deno_path or '未找到'}",
        f"Data: {data_path}",
    ))


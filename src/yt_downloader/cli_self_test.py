"""Minimal frozen-package self-test entry point without loading the GUI."""

from __future__ import annotations

import logging

from yt_downloader.infrastructure.logging_config import configure_logging
from yt_downloader.infrastructure.paths import AppPaths
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.infrastructure.self_test import run_packaged_self_test
from yt_downloader.services.ffmpeg_service import FfmpegService


logger = logging.getLogger(__name__)


def main() -> int:
    paths = AppPaths.discover()
    paths.ensure()
    configure_logging(paths.logs)
    try:
        run_packaged_self_test(
            cache_directory=paths.cache,
            ffmpeg=FfmpegService(),
            deno_path=find_tool("deno"),
        )
        return 0
    except Exception:
        logger.exception("Packaged self-test failed")
        return 2

"""Application-owned paths; never scans outside these locations."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    data: Path
    settings: Path
    history: Path
    logs: Path
    cache: Path
    thumbnails: Path

    @classmethod
    def discover(cls, root: str | Path | None = None) -> "AppPaths":
        if root is None:
            override = os.environ.get("YT_DOWNLOADER_DATA_DIR")
            local = os.environ.get("LOCALAPPDATA")
            root = Path(override) if override else (Path(local) / "YTDownloader" if local else Path.home() / "AppData" / "Local" / "YTDownloader")
        data = Path(root)
        return cls(data, data / "settings.json", data / "history.db", data / "logs", data / "cache", data / "cache" / "thumbnails")

    def ensure(self) -> None:
        for directory in (self.data, self.logs, self.cache, self.thumbnails):
            directory.mkdir(parents=True, exist_ok=True)


def default_videos_directory() -> Path:
    override = os.environ.get("YT_DOWNLOADER_VIDEOS_DIR")
    if override:
        videos = Path(override)
        videos.mkdir(parents=True, exist_ok=True)
        return videos
    profile = Path(os.environ.get("USERPROFILE") or Path.home())
    videos = profile / "Videos"
    videos.mkdir(parents=True, exist_ok=True)
    return videos

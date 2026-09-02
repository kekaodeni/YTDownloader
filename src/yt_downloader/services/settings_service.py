"""Small, versioned, atomic JSON settings persistence."""

from __future__ import annotations

from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
from typing import Any

from yt_downloader.core.models import AppSettings


logger = logging.getLogger(__name__)
_THEMES = {"system", "light", "dark"}


class SettingsService:
    def __init__(self, path: str | Path, *, default_download_directory: str | Path) -> None:
        self.path = Path(path)
        self.default_download_directory = Path(default_download_directory)

    def defaults(self) -> AppSettings:
        return AppSettings(download_directory=str(self.default_download_directory))

    def load(self) -> AppSettings:
        if not self.path.exists():
            return self.defaults()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return self._from_mapping(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring invalid settings file %s: %s", self.path, exc)
            return self.defaults()

    def _from_mapping(self, data: Any) -> AppSettings:
        if not isinstance(data, dict) or int(data.get("schema_version", 1)) != 1:
            raise ValueError("unsupported settings schema")
        theme = str(data.get("theme", "system"))
        if theme not in _THEMES:
            raise ValueError("invalid theme")
        directory = str(data.get("download_directory") or self.default_download_directory)
        quality = str(data.get("default_quality") or "recommended")
        return AppSettings(
            schema_version=1,
            download_directory=directory,
            default_quality=quality,
            theme=theme,
            reduce_motion=bool(data.get("reduce_motion", False)),
            ffmpeg_directory=str(data.get("ffmpeg_directory") or ""),
        )

    def save(self, settings: AppSettings) -> None:
        if settings.theme not in _THEMES:
            raise ValueError("外观主题设置无效。")
        if not settings.download_directory.strip():
            raise ValueError("默认下载目录不能为空。")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)


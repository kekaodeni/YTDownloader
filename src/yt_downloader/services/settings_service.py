"""Small, versioned, atomic JSON settings persistence."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
import logging
import os
from pathlib import Path
from typing import Any

from yt_downloader.core.models import AppSettings


logger = logging.getLogger(__name__)
_THEMES = {"system", "light", "dark"}
_PROXY_MODES = {"system", "direct", "custom"}
_FRAGMENT_COUNTS = {0, 1, 2, 4, 8}


class SettingsService:
    def __init__(self, path: str | Path, *, default_download_directory: str | Path) -> None:
        self.path = Path(path)
        self.default_download_directory = Path(default_download_directory)
        self._migration_pending = False

    def defaults(self) -> AppSettings:
        return AppSettings(download_directory=str(self.default_download_directory))

    def load(self) -> AppSettings:
        if not self.path.exists():
            return self.defaults()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            settings, source_schema = self._from_mapping(data)
            self._migration_pending = source_schema == 1
            return settings
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring invalid settings file %s: %s", self.path, exc)
            return self.defaults()

    def _from_mapping(self, data: Any) -> tuple[AppSettings, int]:
        if not isinstance(data, dict):
            raise ValueError("settings root must be an object")
        source_schema = int(data.get("schema_version", 1))
        if source_schema not in {1, 2}:
            raise ValueError("unsupported settings schema")
        theme = str(data.get("theme", "system"))
        if theme not in _THEMES:
            raise ValueError("invalid theme")
        directory = str(data.get("download_directory") or self.default_download_directory)
        quality = str(data.get("default_quality") or "recommended")
        proxy_mode = str(data.get("proxy_mode") or "system")
        if proxy_mode not in _PROXY_MODES:
            raise ValueError("invalid proxy mode")
        concurrent_fragments = int(data.get("concurrent_fragments", 0))
        if concurrent_fragments not in _FRAGMENT_COUNTS:
            raise ValueError("invalid fragment concurrency")
        return AppSettings(
            schema_version=2,
            download_directory=directory,
            default_quality=quality,
            theme=theme,
            reduce_motion=bool(data.get("reduce_motion", False)),
            ffmpeg_directory=str(data.get("ffmpeg_directory") or ""),
            proxy_mode=proxy_mode,
            custom_proxy_url=str(data.get("custom_proxy_url") or ""),
            concurrent_fragments=concurrent_fragments,
        ), source_schema

    def save(self, settings: AppSettings) -> None:
        self.validate(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        normalized = replace(settings, schema_version=2)
        payload = json.dumps(asdict(normalized), ensure_ascii=False, indent=2) + "\n"
        backup = self.path.with_name("settings.v1.backup.json")
        backup_temporary = backup.with_suffix(backup.suffix + ".tmp")
        try:
            if self._migration_pending and self.path.is_file() and not backup.exists():
                with self.path.open("rb") as source, backup_temporary.open("wb") as destination:
                    while chunk := source.read(64 * 1024):
                        destination.write(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
                os.replace(backup_temporary, backup)
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self._migration_pending = False
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            if backup_temporary.exists():
                backup_temporary.unlink(missing_ok=True)

    def validate(self, settings: AppSettings) -> None:
        if settings.theme not in _THEMES:
            raise ValueError("外观主题设置无效。")
        if not settings.download_directory.strip():
            raise ValueError("默认下载目录不能为空。")
        if settings.proxy_mode not in _PROXY_MODES:
            raise ValueError("代理模式无效。")
        if settings.concurrent_fragments not in _FRAGMENT_COUNTS:
            raise ValueError("分片并发设置无效。")
        directory = Path(settings.download_directory).expanduser()
        if not directory.is_absolute():
            raise ValueError("默认下载目录必须是绝对路径。")
        existing = directory
        while not existing.exists() and existing.parent != existing:
            existing = existing.parent
        if not existing.exists() or not existing.is_dir() or not os.access(existing, os.W_OK):
            raise ValueError("默认下载目录的上级目录不存在或不可写。")

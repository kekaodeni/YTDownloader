"""Small, versioned, atomic JSON settings persistence."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
import logging
import os
from pathlib import Path
from typing import Any

from yt_downloader.core.models import AppSettings, CodecPreference, DownloadProfile, SUPPORTED_LOCALES
from yt_downloader.services.download_profiles import (
    BUILTIN_PROFILE_IDS,
    profile_from_mapping,
    profiles_by_id,
    validate_profile,
)
from yt_downloader.services.network_policy import NetworkPolicy


logger = logging.getLogger(__name__)
_THEMES = {"system", "light", "dark"}
_PROXY_MODES = {"system", "direct", "custom"}
_FRAGMENT_COUNTS = {0, 1, 2, 4, 8}
_QUALITY_ALIASES = {
    'recommended': 'recommended', 'auto': 'recommended', 'highest': 'highest',
    '2160p': '2160p', '1440p': '1440p', '1080p': '1080p', '720p': '720p',
    '2160p 4K': '2160p', '1440p 2K': '1440p', '1080': '1080p',
}


class SettingsService:
    def __init__(self, path: str | Path, *, default_download_directory: str | Path) -> None:
        self.path = Path(path)
        self.default_download_directory = Path(default_download_directory)
        self._migration_pending = False
        self._migration_source_schema: int | None = None

    def defaults(self) -> AppSettings:
        return AppSettings(download_directory=str(self.default_download_directory))

    def load(self) -> AppSettings:
        if not self.path.exists():
            return self.defaults()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            settings, source_schema = self._from_mapping(data)
            self._migration_pending = source_schema < 7
            self._migration_source_schema = source_schema if source_schema < 7 else None
            return settings
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring invalid settings file %s: %s", self.path, exc)
            return self.defaults()

    def _from_mapping(self, data: Any) -> tuple[AppSettings, int]:
        if not isinstance(data, dict):
            raise ValueError("settings root must be an object")
        source_schema = int(data.get("schema_version", 1))
        if source_schema not in {1, 2, 3, 4, 5, 6, 7}:
            raise ValueError("unsupported settings schema")
        theme = str(data.get("theme", "system"))
        if theme not in _THEMES:
            raise ValueError("invalid theme")
        directory = str(data.get("download_directory") or self.default_download_directory)
        quality = _QUALITY_ALIASES.get(str(data.get('default_quality') or 'recommended'), 'recommended')
        proxy_mode = str(data.get("proxy_mode") or "system")
        if proxy_mode not in _PROXY_MODES:
            raise ValueError("invalid proxy mode")
        custom_proxy_url = str(data.get("custom_proxy_url") or "")
        NetworkPolicy(proxy_mode, custom_proxy_url).snapshot()
        concurrent_fragments = int(data.get("concurrent_fragments", 0))
        if concurrent_fragments not in _FRAGMENT_COUNTS:
            raise ValueError("invalid fragment concurrency")
        maximum = data.get('max_concurrent_downloads', 2)
        if type(maximum) is not int or maximum not in {1, 2, 3, 4}:
            raise ValueError('invalid download concurrency')
        try:
            codec_preference = CodecPreference(str(data.get("codec_preference") or "auto"))
        except ValueError as exc:
            raise ValueError("invalid codec preference") from exc
        custom_profiles: tuple[DownloadProfile, ...] = ()
        default_profile_id = 'auto'
        # V2 deliberately uses new keys. V1 development-only keys are ignored.
        raw_profiles = data.get('custom_download_profiles') if source_schema >= 6 else None
        if isinstance(raw_profiles, list):
            profiles = []
            seen_profile_ids = set()
            for item in raw_profiles:
                try:
                    profile = profile_from_mapping(item)
                except (TypeError, ValueError) as exc:
                    logger.warning('Ignoring invalid semantic download profile: %s', exc)
                    continue
                if profile.id in seen_profile_ids:
                    logger.warning('Ignoring duplicate semantic download profile %s', profile.id)
                    continue
                seen_profile_ids.add(profile.id)
                profiles.append(profile)
            custom_profiles = tuple(profiles)
        raw_default_profile_id = str(data.get('default_download_profile_id') or '') if source_schema >= 6 else ''
        profile_index = profiles_by_id(custom_profiles)
        if raw_default_profile_id in profile_index:
            default_profile_id = raw_default_profile_id
        elif not custom_profiles:
            old_quality = quality
            try:
                old_codec = CodecPreference(str(data.get('codec_preference') or 'auto')).value
            except ValueError:
                old_codec = 'auto'
            if old_quality != 'recommended' or old_codec != 'auto':
                migrated = DownloadProfile(
                    id='migrated-default', name='迁移的默认设置',
                    quality_tier=old_quality if old_quality in {'highest', '2160p', '1440p', '1080p', '720p'} else 'recommended',
                    codec_preference=old_codec,
                )
                custom_profiles = (migrated,)
                default_profile_id = migrated.id
        return AppSettings(
            schema_version=7,
            download_directory=directory,
            theme=theme,
            reduce_motion=bool(data.get("reduce_motion", False)),
            ffmpeg_directory=str(data.get("ffmpeg_directory") or ""),
            proxy_mode=proxy_mode,
            custom_proxy_url=custom_proxy_url,
            concurrent_fragments=concurrent_fragments,
            max_concurrent_downloads=maximum,
            auto_check_updates=bool(data.get("auto_check_updates", True)),
            use_cookies=(bool(data.get('use_cookies', False)) if source_schema >= 5
                         else bool(data.get('default_cookie_profile_id'))),
            default_download_profile_id=default_profile_id,
            custom_download_profiles=custom_profiles,
            language=(str(data.get('language') or 'zh-CN') if str(data.get('language') or 'zh-CN') in SUPPORTED_LOCALES else 'zh-CN'),
            prevent_duplicate_downloads=bool(data.get('prevent_duplicate_downloads', True)),
            system_notifications=bool(data.get('system_notifications', True)),
        ), source_schema

    def save(self, settings: AppSettings) -> None:
        self.validate(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        normalized = replace(settings, schema_version=7)
        payload = json.dumps(asdict(normalized), ensure_ascii=False, indent=2) + "\n"
        source_schema = self._migration_source_schema or 2
        backup = self.path.with_name(f"settings.v{source_schema}.backup.json")
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
            self._migration_source_schema = None
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            if backup_temporary.exists():
                backup_temporary.unlink(missing_ok=True)

    def validate(self, settings: AppSettings) -> None:
        if settings.language not in SUPPORTED_LOCALES:
            raise ValueError('界面语言设置无效。')
        if settings.theme not in _THEMES:
            raise ValueError("外观主题设置无效。")
        if not settings.download_directory.strip():
            raise ValueError("默认下载目录不能为空。")
        if settings.proxy_mode not in _PROXY_MODES:
            raise ValueError("代理模式无效。")
        if type(settings.max_concurrent_downloads) is not int or settings.max_concurrent_downloads not in {1, 2, 3, 4}:
            raise ValueError('同时下载任务数必须为 1–4。')
        if settings.concurrent_fragments not in _FRAGMENT_COUNTS:
            raise ValueError("分片并发设置无效。")
        profile_index = profiles_by_id(settings.custom_download_profiles)
        if settings.default_download_profile_id not in profile_index:
            raise ValueError('默认下载预设无效。')
        ids = set()
        for profile in settings.custom_download_profiles:
            validate_profile(profile)
            if profile.id in ids:
                raise ValueError('自定义下载预设标识重复。')
            ids.add(profile.id)
        NetworkPolicy(settings.proxy_mode, settings.custom_proxy_url).snapshot()
        directory = Path(settings.download_directory).expanduser()
        if not directory.is_absolute():
            raise ValueError("默认下载目录必须是绝对路径。")
        existing = directory
        while not existing.exists() and existing.parent != existing:
            existing = existing.parent
        if not existing.exists() or not existing.is_dir() or not os.access(existing, os.W_OK):
            raise ValueError("默认下载目录的上级目录不存在或不可写。")

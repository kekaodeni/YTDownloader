"""Small, independent persistence and runtime capability policy for updates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Mapping

from yt_downloader.updates.models import UpdateCapability


@dataclass(frozen=True, slots=True)
class UpdatePersistentState:
    schema_version: int = 1
    last_checked_at: str = ''
    last_error: str = ''
    remind_after: str = ''
    highest_verified_version: str = ''
    transaction_id: str = ''
    pending_version: str = ''


class UpdateStateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> UpdatePersistentState:
        if not self.path.is_file():
            return UpdatePersistentState()
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(payload, dict) or payload.get('schema_version') != 1:
                raise ValueError('unsupported update state')
            allowed = set(UpdatePersistentState.__dataclass_fields__)
            if set(payload) - allowed:
                raise ValueError('unknown update state fields')
            return UpdatePersistentState(**payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return UpdatePersistentState()

    def save(self, state: UpdatePersistentState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        try:
            with temporary.open('w', encoding='utf-8', newline='\n') as handle:
                json.dump(asdict(state), handle, ensure_ascii=False, indent=2)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def should_auto_check(self, now: datetime) -> bool:
        value = self.load().last_checked_at
        if not value:
            return True
        try:
            checked = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if checked.tzinfo is None or now.tzinfo is None:
                return True
            return now >= checked + timedelta(hours=24)
        except ValueError:
            return True


def detect_update_capability(
    *,
    frozen: bool | None = None,
    build_info_path: Path | None = None,
    updater_path: Path | None = None,
    trusted_keys: Mapping[str, bytes] | None = None,
) -> UpdateCapability:
    is_frozen = bool(getattr(sys, 'frozen', False)) if frozen is None else frozen
    if not is_frozen:
        return UpdateCapability.CHECK_ONLY
    build_info_path = build_info_path or (Path(sys.executable).parent / 'BUILD-INFO.json')
    updater_path = updater_path or (Path(sys.executable).parent / 'YTDownloaderUpdater.exe')
    try:
        build_info = json.loads(build_info_path.read_text(encoding='utf-8-sig'))
        validation_only = build_info.get('validation_only') is True
    except (OSError, ValueError, json.JSONDecodeError):
        return UpdateCapability.CHECK_ONLY
    if validation_only or not updater_path.is_file() or not trusted_keys:
        return UpdateCapability.DOWNLOAD_AND_VERIFY
    return UpdateCapability.AUTO_INSTALL

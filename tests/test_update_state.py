from datetime import datetime, timedelta, timezone
import json

from yt_downloader.updates.models import UpdateCapability
from yt_downloader.updates.state import UpdatePersistentState, UpdateStateStore, detect_update_capability


def test_update_state_is_atomic_and_throttles_automatic_checks(tmp_path):
    path = tmp_path / 'update-state.json'
    store = UpdateStateStore(path)
    now = datetime(2026, 9, 4, 10, tzinfo=timezone.utc)
    assert store.should_auto_check(now)
    state = UpdatePersistentState(last_checked_at=now.isoformat(), highest_verified_version='0.4.1')
    store.save(state)
    assert store.load() == state
    assert not store.should_auto_check(now + timedelta(hours=23, minutes=59))
    assert store.should_auto_check(now + timedelta(hours=24))
    assert not path.with_suffix('.tmp').exists()


def test_update_state_recovers_from_invalid_json(tmp_path):
    path = tmp_path / 'update-state.json'; path.write_text('{broken', encoding='utf-8')
    assert UpdateStateStore(path).load() == UpdatePersistentState()


def test_capabilities_keep_source_and_validation_builds_out_of_auto_install(tmp_path):
    updater = tmp_path / 'YTDownloaderUpdater.exe'; updater.write_bytes(b'updater')
    validation = tmp_path / 'validation.json'
    validation.write_text(json.dumps({'validation_only': True}), encoding='utf-8')
    production = tmp_path / 'production.json'
    production.write_text(json.dumps({'validation_only': False}), encoding='utf-8')

    assert detect_update_capability(frozen=False, build_info_path=production, updater_path=updater, trusted_keys={'prod': b'x' * 32}) is UpdateCapability.CHECK_ONLY
    assert detect_update_capability(frozen=True, build_info_path=validation, updater_path=updater, trusted_keys={'prod': b'x' * 32}) is UpdateCapability.DOWNLOAD_AND_VERIFY
    assert detect_update_capability(frozen=True, build_info_path=production, updater_path=updater, trusted_keys={}) is UpdateCapability.DOWNLOAD_AND_VERIFY
    assert detect_update_capability(frozen=True, build_info_path=production, updater_path=updater, trusted_keys={'prod': b'x' * 32}) is UpdateCapability.AUTO_INSTALL


def test_capability_uses_internal_helper_layout_from_build_metadata(tmp_path):
    root = tmp_path / 'install'; (root / '_internal' / 'updater').mkdir(parents=True)
    info = root / 'BUILD-INFO.json'; info.write_text(json.dumps({'validation_only': False, 'helper_layout': 'internal-v1'}))
    (root / '_internal' / 'updater' / 'YTDownloaderUpdater.exe').write_bytes(b'helper')
    assert detect_update_capability(frozen=True, build_info_path=info, trusted_keys={'prod': b'x' * 32}) is UpdateCapability.AUTO_INSTALL

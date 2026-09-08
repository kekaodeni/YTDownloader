import json
from pathlib import Path

import pytest

from yt_downloader.updates.transaction import (
    InstallPreflight,
    TransactionalInstaller,
    UpdateTransactionStage,
    wait_for_health,
)


def _install_tree(root: Path, version: str) -> None:
    root.mkdir()
    files = {
        'YTDownloader.exe': version.encode(),
        'YTDownloaderUpdater.exe': b'updater',
        'BUILD-INFO.json': json.dumps({'app_version': version}).encode(),
    }
    for name, payload in files.items():
        (root / name).write_bytes(payload)
    sums = [
        {'Path': name, 'SHA256': __import__('hashlib').sha256(payload).hexdigest()}
        for name, payload in files.items()
    ]
    (root / 'SHA256SUMS.json').write_text(json.dumps(sums), encoding='utf-8')


def test_preflight_rejects_unknown_install_files_and_user_data_overlap(tmp_path):
    install = tmp_path / 'app'; _install_tree(install, 'old')
    (install / 'unknown.txt').write_text('mine')
    with pytest.raises(ValueError, match='unknown'):
        InstallPreflight().validate(install, tmp_path / 'data', required_bytes=1)
    (install / 'unknown.txt').unlink()
    with pytest.raises(ValueError, match='overlap'):
        InstallPreflight().validate(install, install / 'data', required_bytes=1)


def test_transaction_switches_directories_only_after_process_exit_and_health(tmp_path):
    install = tmp_path / 'app'; candidate = tmp_path / 'candidate'
    _install_tree(install, 'old'); _install_tree(candidate, 'new')
    staging = tmp_path / 'staging'; staging.mkdir()
    events = []
    installer = TransactionalInstaller(
        wait_for_exit=lambda pid, timeout: events.append(('wait', pid, timeout)) or True,
        launch_health_check=lambda exe, tx, marker: events.append(('launch', exe.name, tx)) or marker.write_text('ok') or object(),
        wait_for_health=lambda marker, process, timeout, expected, tx: marker.read_text() == 'ok' and expected == 'new' and tx == 'tx1',
        terminate_launched=lambda process: events.append(('terminate', process)),
    )
    journal = installer.install(
        transaction_id='tx1', install_dir=install, candidate_dir=candidate,
        staging_dir=staging, data_dir=tmp_path / 'data', original_pid=123,
    )
    assert (install / 'YTDownloader.exe').read_bytes() == b'new'
    assert journal.stage is UpdateTransactionStage.COMMITTED
    assert events[0] == ('wait', 123, 30)
    assert not any(e[0] == 'terminate' for e in events)


def test_transaction_rolls_back_when_new_version_has_no_health_confirmation(tmp_path):
    install = tmp_path / 'app'; candidate = tmp_path / 'candidate'
    _install_tree(install, 'old'); _install_tree(candidate, 'new')
    staging = tmp_path / 'staging'; staging.mkdir()
    process = object(); terminated = []
    installer = TransactionalInstaller(
        wait_for_exit=lambda *_: True,
        launch_health_check=lambda *_: process,
        wait_for_health=lambda *_: False,
        terminate_launched=lambda child: terminated.append(child),
    )
    with pytest.raises(RuntimeError, match='health'):
        installer.install(
            transaction_id='tx2', install_dir=install, candidate_dir=candidate,
            staging_dir=staging, data_dir=tmp_path / 'data', original_pid=123,
        )
    assert (install / 'YTDownloader.exe').read_bytes() == b'old'
    assert terminated == [process]
    saved = json.loads((staging / 'update-transaction.json').read_text(encoding='utf-8'))
    assert saved['stage'] == 'ROLLED_BACK'


def test_transaction_stops_without_switching_when_original_process_is_busy(tmp_path):
    install = tmp_path / 'app'; candidate = tmp_path / 'candidate'
    _install_tree(install, 'old'); _install_tree(candidate, 'new')
    staging = tmp_path / 'staging'; staging.mkdir()
    installer = TransactionalInstaller(wait_for_exit=lambda *_: False)
    with pytest.raises(TimeoutError):
        installer.install(
            transaction_id='tx3', install_dir=install, candidate_dir=candidate,
            staging_dir=staging, data_dir=tmp_path / 'data', original_pid=123,
        )
    assert (install / 'YTDownloader.exe').read_bytes() == b'old'
    assert (candidate / 'YTDownloader.exe').read_bytes() == b'new'


def test_health_confirmation_is_bound_to_expected_version(tmp_path):
    marker = tmp_path / 'startup-health.json'
    marker.write_text(json.dumps({
        'status': 'ok', 'transaction_id': 'tx', 'app_version': '0.4.0',
    }), encoding='utf-8')
    process = type('Process', (), {'poll': lambda self: None})()
    assert wait_for_health(marker, process, 1, '0.4.1', 'tx') is False
    assert wait_for_health(marker, process, 1, '0.4.0', 'different-tx') is False


def test_recovery_is_idempotent_after_candidate_was_installed(tmp_path):
    install = tmp_path / 'app'; candidate = tmp_path / 'candidate'; backup = tmp_path / '.app.backup-tx4'
    _install_tree(install, 'new'); _install_tree(backup, 'old')
    staging = tmp_path / 'staging'; staging.mkdir()
    journal = {
        'transaction_id': 'tx4', 'stage': 'WAITING_FOR_HEALTH',
        'install_dir': str(install), 'candidate_dir': str(candidate),
        'backup_dir': str(backup), 'health_marker': str(staging / 'startup-health.json'), 'error': '',
    }
    (staging / 'update-transaction.json').write_text(json.dumps(journal), encoding='utf-8')
    installer = TransactionalInstaller()
    first = installer.recover(staging)
    second = installer.recover(staging)
    assert first.stage is UpdateTransactionStage.ROLLED_BACK
    assert second.stage is UpdateTransactionStage.ROLLED_BACK
    assert (install / 'YTDownloader.exe').read_bytes() == b'old'
    assert (candidate / 'YTDownloader.exe').read_bytes() == b'new'

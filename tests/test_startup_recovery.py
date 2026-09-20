import json
from pathlib import Path

import pytest

from test_update_bridge_install import staged_service, write_tree
from yt_downloader.updates.archive import SafePackageExtractor as Archive


def interrupted(tmp_path, current='0.4.2', target='0.5.0', stage='WAITING_FOR_HEALTH'):
    service, install, data, transaction = staged_service(tmp_path, current, target)
    command = service.prepare_install_command(install, data, 42)
    backup = install.parent / f'.{install.name}.backup-{transaction.name}'
    candidate = install.parent / f'.{install.name}.candidate-{transaction.name}'
    if stage not in {'PREPARED', 'WAITING_FOR_EXIT'}:
        install.rename(backup)
        write_tree(install, target)
    binding = json.loads((transaction/'install-request.json').read_text())
    journal = dict(schema_version=2, transaction_id=transaction.name, stage=stage,
                   install_dir=str(install), candidate_dir=str(candidate), backup_dir=str(backup),
                   health_marker=str(transaction/'startup-health.json'), source_version=current,
                   target_version=target, source_layout='legacy-root' if current == '0.4.2' else 'internal-v1',
                   target_layout='internal-v1', manifest_sha256=binding['manifest_sha256'],
                   package_sha256=binding['package_sha256'], error='')
    (transaction/'update-transaction.json').write_text(json.dumps(journal))
    return service, install, data, transaction


def test_startup_prepares_external_recovery_without_mutating_installed_tree(tmp_path):
    from yt_downloader.updates.recovery import pending_recovery, prepare_recovery
    service, install, data, transaction = interrupted(tmp_path)
    before = {p.relative_to(install).as_posix(): Archive.file_hash(p) for p in install.rglob('*') if p.is_file()}
    request = pending_recovery(install, data)
    assert request.transaction == transaction
    command = prepare_recovery(request, service.keyring, helper_version='0.5.0', parent_pid=99)
    assert Path(command[0]) == transaction/'recovery-helper/YTDownloaderUpdater.exe'
    assert '--recover' in command
    assert command[command.index('--recovery-parent-pid')+1] == '99'
    after = {p.relative_to(install).as_posix(): Archive.file_hash(p) for p in install.rglob('*') if p.is_file()}
    assert before == after


def test_external_recovery_waits_for_parent_before_switch_and_relaunch(tmp_path, monkeypatch):
    from yt_downloader.updates.recovery import pending_recovery, prepare_recovery
    from yt_downloader_updater import __main__ as entry
    service, install, data, transaction = interrupted(tmp_path)
    request = pending_recovery(install, data)
    command = prepare_recovery(request, service.keyring, helper_version='0.5.0', parent_pid=99)
    monkeypatch.setattr(entry, 'PRODUCTION_TRUSTED_KEYS', {'test': b'x'*32})
    monkeypatch.setattr(entry, 'TrustedKeyring', lambda _: service.keyring)
    monkeypatch.setattr(entry, 'UPDATER_VERSION', '0.5.0')
    monkeypatch.setattr(entry.sys, 'executable', command[0])
    events = []
    def wait(pid, seconds):
        assert (install/'YTDownloader.exe').read_bytes() == b'0.5.0'
        events.append(('wait', pid))
        return True
    monkeypatch.setattr(entry, 'wait_for_process_exit', wait, raising=False)
    def launch(executable, **kwargs):
        assert (install/'YTDownloader.exe').read_bytes() == b'0.4.2'
        events.append(('launch', executable))
    monkeypatch.setattr(entry, 'launch_recovered_application', launch, raising=False)
    assert entry.run(list(command[1:])) == 0
    assert events[0] == ('wait', 99)
    assert events[1][0] == 'launch'
    assert json.loads((transaction/'update-transaction.json').read_text())['stage'] == 'ROLLED_BACK'


def test_recovery_before_directory_switch_finishes_aborted_transaction(tmp_path):
    from yt_downloader.updates.transaction import TransactionalInstaller
    from yt_downloader.updates.recovery import pending_recovery
    service, install, data, transaction = interrupted(tmp_path, current='0.5.0', target='0.5.1', stage='WAITING_FOR_EXIT')
    result = TransactionalInstaller().recover(transaction)
    assert result.stage.value == 'ROLLED_BACK'
    assert pending_recovery(install, data) is None
    assert (install/'YTDownloader.exe').read_bytes() == b'0.5.0'


@pytest.mark.parametrize('damage', ['signature', 'package', 'helper', 'journal_path', 'journal_hash'])
def test_recovery_rejects_tampered_inputs_before_install_mutation(tmp_path, damage):
    from yt_downloader.updates.recovery import pending_recovery, prepare_recovery
    service, install, data, transaction = interrupted(tmp_path)
    request = pending_recovery(install, data)
    if damage == 'signature':
        (transaction/'update-manifest.sig').write_bytes(b'bad')
    elif damage == 'package':
        service.verified_package.path.write_bytes(b'bad')
    elif damage == 'helper':
        (install/'_internal/updater/YTDownloaderUpdater.exe').write_bytes(b'bad')
    else:
        journal = json.loads((transaction/'update-transaction.json').read_text())
        journal['candidate_dir' if damage == 'journal_path' else 'package_sha256'] = str(tmp_path/'unowned')
        (transaction/'update-transaction.json').write_text(json.dumps(journal))
    before = (install/'YTDownloader.exe').read_bytes()
    with pytest.raises((ValueError, OSError)):
        prepare_recovery(request, service.keyring, helper_version='0.5.0', parent_pid=99)
    assert (install/'YTDownloader.exe').read_bytes() == before
    assert not (transaction/'recovery-helper').exists()


def test_download_only_transaction_remains_available_to_normal_revalidation(tmp_path):
    from yt_downloader.updates.recovery import pending_recovery
    service, install, data, transaction = staged_service(tmp_path)
    assert pending_recovery(install, data) is None
    assert service.verified_package.path.is_file()


def test_normal_frozen_startup_dispatches_recovery_before_history_or_updates(tmp_path, monkeypatch):
    from yt_downloader import app
    from yt_downloader.infrastructure.paths import AppPaths
    service, install, data, transaction = interrupted(tmp_path)
    monkeypatch.setattr(app.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(app.sys, 'executable', str(install/'YTDownloader.exe'))
    monkeypatch.setattr(app.AppPaths, 'discover', lambda: AppPaths.discover(data))
    # Retain the actual path constructor without recursively calling the patched method.
    paths = AppPaths(data, data/'settings.json', data/'history.db', data/'logs', data/'cache', data/'cache/thumbnails')
    monkeypatch.setattr(app.AppPaths, 'discover', lambda: paths)
    calls = []
    monkeypatch.setattr(app, 'create_application', lambda *a: (_ for _ in ()).throw(AssertionError('Normal controller started before recovery')))
    from yt_downloader.ui import startup_recovery
    monkeypatch.setattr(startup_recovery, 'run_recovery_startup', lambda paths, request, error=None: calls.append(request) or 0)
    assert app.main([]) == 0
    assert calls[0].transaction == transaction


@pytest.mark.parametrize('stage', ['WAITING_FOR_EXIT', 'ORIGINAL_BACKED_UP', 'CANDIDATE_INSTALLED', 'WAITING_FOR_HEALTH', 'ROLLING_BACK', 'ROLLBACK_FAILED'])
def test_recovery_fault_windows_preserve_user_data_and_are_idempotent(tmp_path, stage):
    from yt_downloader.updates.transaction import TransactionalInstaller
    from yt_downloader.updates.recovery import pending_recovery, prepare_recovery
    service, install, data, transaction = interrupted(tmp_path, current='0.5.0', target='0.5.1', stage=stage)
    (data/'settings.json').write_text('{"schema_version":4,"download_directory":"fixture"}')
    from yt_downloader.services.history_service import HistoryRepository
    from test_history_repository import _record
    from yt_downloader.core.models import TaskStatus
    HistoryRepository(data/'history.db').upsert(_record(data, 'old', TaskStatus.COMPLETED))
    hashes = {name: Archive.file_hash(data/name) for name in ('settings.json', 'history.db')}
    if stage == 'ORIGINAL_BACKED_UP':
        candidate = install.parent/f'.{install.name}.candidate-{transaction.name}'
        install.rename(candidate)  # Simulates the gap before the candidate switch.
    result = TransactionalInstaller().recover(transaction)
    assert result.stage.value == 'ROLLED_BACK'
    assert TransactionalInstaller().recover(transaction).stage.value == 'ROLLED_BACK'
    Archive.validate_tree(install, expected_version='0.5.0')
    assert {name: Archive.file_hash(data/name) for name in hashes} == hashes
    assert pending_recovery(install, data) is None


def test_recovery_ui_failure_keeps_diagnostics_available(quick_window):
    from yt_downloader.ui.startup_recovery import RecoveryStartup
    from PySide6.QtWidgets import QApplication
    from yt_downloader.core.errors import AppError
    controller = RecoveryStartup(QApplication.instance(), quick_window, None)
    assert quick_window.state['recoveryBusy']
    controller.failed(AppError('fixture', 'Failure', 'controlled diagnostic'))
    assert not quick_window.state['recoveryBusy']
    assert quick_window.state['recoveryVisible']
    controller.show_details()
    assert controller.error_dialog.state['open']
    assert controller.error_dialog.state['details'] == 'controlled diagnostic'


def test_rolled_back_transaction_is_not_offered_for_install_again(tmp_path):
    from yt_downloader.updates.state import UpdatePersistentState
    from yt_downloader.updates.transaction import TransactionalInstaller
    service, install, data, transaction = interrupted(tmp_path, current='0.5.0', target='0.5.1', stage='WAITING_FOR_EXIT')
    service.state_store.save(UpdatePersistentState(transaction_id='test', pending_version='0.5.1'))
    TransactionalInstaller().recover(transaction)
    service.verified_package = None
    assert service.restore_verified_package() is False
    assert service.state_store.load().pending_version == ''


def test_health_exception_stops_candidate_before_rollback(tmp_path):
    from yt_downloader.updates.transaction import TransactionalInstaller
    install = write_tree(tmp_path/'app', '0.5.0')
    candidate = write_tree(tmp_path/'candidate', '0.5.1')
    staging = tmp_path/'staging'; staging.mkdir()
    stopped = []
    process = object()
    def fail(*args): raise OSError('health transport failure')
    installer = TransactionalInstaller(wait_for_exit=lambda *a: True, launch_health_check=lambda *a: process,
                                       wait_for_health=fail, terminate_launched=stopped.append)
    with pytest.raises(OSError):
        installer.install(transaction_id='test', install_dir=install, candidate_dir=candidate,
                          staging_dir=staging, data_dir=tmp_path/'data', original_pid=1)
    assert stopped == [process]
    Archive.validate_tree(install, expected_version='0.5.0')


def test_recorded_candidate_identity_does_not_kill_other_process(tmp_path):
    import subprocess
    import sys
    from yt_downloader.updates.processes import process_identity, stop_recorded_process
    process = subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
    try:
        identity = process_identity(process.pid)
        altered = dict(identity, created=identity['created']+1)
        assert not stop_recorded_process(altered, Path(sys.executable))
        assert process.poll() is None
        assert stop_recorded_process(identity, Path(sys.executable))
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill();process.wait(timeout=5)


def test_process_wait_does_not_treat_access_denied_as_exited(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from yt_downloader.updates.transaction import wait_for_process_exit
    functions = {name: (lambda *a: 0) for name in ('OpenProcess','CloseHandle','QueryFullProcessImageNameW',
                 'GetProcessTimes','TerminateProcess','WaitForSingleObject')}
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(**functions))
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5)
    with pytest.raises(OSError):
        wait_for_process_exit(987654, 1)

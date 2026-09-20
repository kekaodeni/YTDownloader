"""External updater entry point. This process intentionally has no Qt dependency."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import os
import subprocess

from semver import Version

from yt_downloader.updates.archive import SafePackageExtractor
from yt_downloader import __version__
from yt_downloader.updates.installation import InstallRequest, checked_path, validate_request
from yt_downloader.updates.protocol import compatible
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.transaction import InstallPreflight, TransactionalInstaller, wait_for_process_exit
from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS


UPDATER_VERSION = __version__
REPOSITORY = 'kekaodeni/YTDownloader'


def validate_upgrade_versions(current_value: str, target_value: str) -> tuple[Version, Version]:
    current = Version.parse(current_value)
    target = Version.parse(target_value)
    if target <= current:
        raise ValueError('The signed update version must be newer than the installed version')
    return current, target


def _arguments(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description='Install a verified YTDownloader update')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--recovery-parent-pid', type=int)
    parser.add_argument('--transaction-dir', required=True, type=Path)
    parser.add_argument('--install-dir', required=True, type=Path)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--original-pid', required=True, type=int)
    parser.add_argument('--current-version', required=True)
    parser.add_argument('--target-version', required=True)
    return parser.parse_args(argv)


def launch_recovered_application(executable, *, data, transaction):
    environment = os.environ.copy()
    environment['YT_DOWNLOADER_DATA_DIR'] = str(data)
    environment['YT_DOWNLOADER_RECOVERY_RESULT'] = transaction.name
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return subprocess.Popen([str(executable)], cwd=executable.parent, env=environment,
                            close_fds=True, creationflags=0x08000000 if sys.platform == 'win32' else 0)


def run(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    if not PRODUCTION_TRUSTED_KEYS:
        raise RuntimeError('Production update trust is not enabled in this build')
    current, target = validate_upgrade_versions(args.current_version, args.target_version)
    transaction = checked_path(args.transaction_dir, exists=True)
    install = checked_path(args.install_dir)
    data = checked_path(args.data_dir)
    request = InstallRequest(transaction, install, data, str(current), str(target), args.original_pid)
    if args.recovery_parent_pid is not None:
        if not args.recover or args.recovery_parent_pid <= 0:
            raise ValueError('Recovery parent requires a valid recovery transaction')
        from yt_downloader.updates.recovery import validate_recovery
        from yt_downloader.updates.installation import atomic_json
        keyring = TrustedKeyring(PRODUCTION_TRUSTED_KEYS)
        validate_recovery(request, keyring, Path(sys.executable), UPDATER_VERSION)
        atomic_json(transaction/f'recovery-handoff-{args.recovery_parent_pid}.json',
                    dict(status='ready', transaction_id=transaction.name, parent_pid=args.recovery_parent_pid,
                         helper_version=UPDATER_VERSION))
        if not wait_for_process_exit(args.recovery_parent_pid, 30):
            raise TimeoutError('Application did not exit before recovery')
        # Recheck after handoff. The helper makes no use of the application's
        # prior verified flag, and keeps rollback/layout ownership checks intact.
        validate_recovery(request, keyring, Path(sys.executable), UPDATER_VERSION)
        try:
            result = TransactionalInstaller().recover(transaction)
        except Exception as error:
            from yt_downloader.services.error_report_service import redact_sensitive
            atomic_json(transaction/'recovery-result.json', dict(status='failed', transaction_id=transaction.name,
                        error=redact_sensitive(str(error))))
            # If a complete tree remains, reopen only a recovery/error shell.
            # A missing or invalid tree is preserved for the staging recovery entry.
            try:
                SafePackageExtractor.validate_tree(install)
            except (OSError, ValueError):
                pass
            else:
                launch_recovered_application(install/'YTDownloader.exe', data=data, transaction=transaction)
            raise
        atomic_json(transaction/'recovery-result.json', dict(status='ok', transaction_id=transaction.name,
                                                            stage=result.stage.value))
        from dataclasses import replace
        from yt_downloader.updates.state import UpdateStateStore
        store = UpdateStateStore(data/'update-state.json')
        saved = store.load()
        if saved.transaction_id == transaction.name.removeprefix('update-') and saved.pending_version == request.target_version:
            store.save(replace(saved, transaction_id='', pending_version=''))
        launch_recovered_application(install/'YTDownloader.exe', data=data, transaction=transaction)
        return 0
    manifest = validate_request(request, TrustedKeyring(PRODUCTION_TRUSTED_KEYS),
                                executing_helper=Path(sys.executable), recovery=args.recover)
    if UPDATER_VERSION != str(current) or not compatible(manifest, str(current), UPDATER_VERSION):
        raise RuntimeError('This updater protocol cannot safely install the selected version')
    if args.recover:
        if not wait_for_process_exit(args.original_pid, 30):
            raise TimeoutError('Original application did not exit before recovery')
        TransactionalInstaller().recover(transaction)
        return 0
    package = transaction / manifest.package.name
    candidate = install.parent / f'.{install.name}.candidate-{transaction.name}'
    backup_size = sum(path.stat().st_size for path in install.rglob('*') if path.is_file())
    InstallPreflight().validate(
        install, args.data_dir,
        required_bytes=manifest.package.compressed_size + manifest.package.extracted_size + backup_size + 64 * 1024 * 1024,
    )
    SafePackageExtractor().extract(
        package, candidate,
        signed_extracted_size=manifest.package.extracted_size,
        expected_version=str(manifest.version),
        expected_layout=manifest.helper_layout,
    )
    TransactionalInstaller().install(
        transaction_id=transaction.name,
        install_dir=install,
        candidate_dir=candidate,
        staging_dir=transaction,
        data_dir=args.data_dir,
        original_pid=args.original_pid,
    )
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f'YTDownloader update failed: {exc}', file=sys.stderr)
        raise SystemExit(2)

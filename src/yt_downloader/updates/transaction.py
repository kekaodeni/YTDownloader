"""Recoverable, same-volume installation transaction used by the external updater."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Callable, Protocol

from yt_downloader.updates.archive import SafePackageExtractor


class UpdateTransactionStage(str, Enum):
    PREPARED = 'PREPARED'
    WAITING_FOR_EXIT = 'WAITING_FOR_EXIT'
    ORIGINAL_BACKED_UP = 'ORIGINAL_BACKED_UP'
    CANDIDATE_INSTALLED = 'CANDIDATE_INSTALLED'
    WAITING_FOR_HEALTH = 'WAITING_FOR_HEALTH'
    COMMITTED = 'COMMITTED'
    ROLLING_BACK = 'ROLLING_BACK'
    ROLLED_BACK = 'ROLLED_BACK'
    ROLLBACK_FAILED = 'ROLLBACK_FAILED'


@dataclass(frozen=True, slots=True)
class UpdateTransactionJournal:
    transaction_id: str
    stage: UpdateTransactionStage
    install_dir: str
    candidate_dir: str
    backup_dir: str
    health_marker: str
    error: str = ''


class _ProcessLike(Protocol):
    def poll(self): ...
    def terminate(self): ...


class InstallPreflight:
    def __init__(self, *, free_space: Callable[[Path], int] | None = None) -> None:
        self.free_space = free_space or (lambda path: shutil.disk_usage(path).free)

    def validate(self, install_dir: Path, data_dir: Path, *, required_bytes: int) -> None:
        install = install_dir.resolve(strict=True)
        data = data_dir.resolve(strict=False)
        if self._contains(install, data) or self._contains(data, install):
            raise ValueError('Application and user data directories overlap')
        SafePackageExtractor.validate_tree(install)
        if self.free_space(install.parent) < max(0, required_bytes):
            raise OSError('Insufficient disk space for candidate, backup, and safety margin')
        probe = install.parent / f'.yt-downloader-write-probe-{os.getpid()}'
        try:
            probe.write_bytes(b'')
        except OSError as exc:
            raise PermissionError('Installation parent directory is not writable') from exc
        finally:
            try:
                probe.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _contains(parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False


class TransactionalInstaller:
    def __init__(
        self,
        *,
        wait_for_exit: Callable[[int, int], bool] | None = None,
        launch_health_check: Callable[[Path, str, Path], object] | None = None,
        wait_for_health: Callable[[Path, object, int], bool] | None = None,
        terminate_launched: Callable[[object], None] | None = None,
        preflight: InstallPreflight | None = None,
        replace_path: Callable[[Path, Path], None] | None = None,
    ) -> None:
        self.wait_for_exit = wait_for_exit or wait_for_process_exit
        self.launch_health_check = launch_health_check or globals()['launch_health_check']
        self.wait_for_health = wait_for_health or globals()['wait_for_health']
        self.terminate_launched = terminate_launched or terminate_launched_process
        self.preflight = preflight or InstallPreflight()
        self.replace_path = replace_path or os.replace

    def install(
        self,
        *,
        transaction_id: str,
        install_dir: Path,
        candidate_dir: Path,
        staging_dir: Path,
        data_dir: Path,
        original_pid: int,
    ) -> UpdateTransactionJournal:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', transaction_id):
            raise ValueError('Invalid update transaction identifier')
        install = install_dir.resolve(strict=True)
        candidate = candidate_dir.resolve(strict=True)
        staging = staging_dir.resolve(strict=True)
        if install.drive.casefold() != candidate.drive.casefold():
            raise ValueError('Candidate and installation must be on the same volume')
        if candidate.parent != install.parent:
            raise ValueError('Candidate must be a sibling of the installation directory')
        SafePackageExtractor.validate_tree(candidate)
        required = self._tree_size(install) + self._tree_size(candidate) + 64 * 1024 * 1024
        self.preflight.validate(install, data_dir, required_bytes=required)
        backup = install.parent / f'.{install.name}.backup-{transaction_id}'
        if backup.exists():
            raise FileExistsError(f'Backup already exists: {backup}')
        health = staging / 'startup-health.json'
        journal_path = staging / 'update-transaction.json'
        lock_path = staging / 'update-transaction.lock'
        lock_fd = self._acquire_lock(lock_path)
        journal = UpdateTransactionJournal(transaction_id, UpdateTransactionStage.PREPARED, str(install), str(candidate), str(backup), str(health))
        self._save(journal_path, journal)
        try:
            journal = self._advance(journal_path, journal, UpdateTransactionStage.WAITING_FOR_EXIT)
            if not self.wait_for_exit(original_pid, 30):
                raise TimeoutError('Original application did not exit within 30 seconds')
            self.replace_path(install, backup)
            journal = self._advance(journal_path, journal, UpdateTransactionStage.ORIGINAL_BACKED_UP)
            try:
                self.replace_path(candidate, install)
                journal = self._advance(journal_path, journal, UpdateTransactionStage.CANDIDATE_INSTALLED)
                process = self.launch_health_check(install / 'YTDownloader.exe', transaction_id, health)
                journal = self._advance(journal_path, journal, UpdateTransactionStage.WAITING_FOR_HEALTH)
                if not self.wait_for_health(health, process, 30):
                    self.terminate_launched(process)
                    raise RuntimeError('New version did not provide startup health confirmation')
                journal = self._advance(journal_path, journal, UpdateTransactionStage.COMMITTED)
                return journal
            except BaseException as exc:
                self._rollback(journal_path, journal, install, candidate, backup, exc)
                raise
        finally:
            os.close(lock_fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def recover(self, staging_dir: Path) -> UpdateTransactionJournal:
        """Idempotently restore the last known-good tree after an interrupted switch."""
        staging = staging_dir.resolve(strict=True)
        path = staging / 'update-transaction.json'
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            journal = UpdateTransactionJournal(
                transaction_id=str(raw['transaction_id']),
                stage=UpdateTransactionStage(raw['stage']),
                install_dir=str(raw['install_dir']),
                candidate_dir=str(raw['candidate_dir']),
                backup_dir=str(raw['backup_dir']),
                health_marker=str(raw['health_marker']),
                error=str(raw.get('error', '')),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError('Update transaction journal is invalid') from exc
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', journal.transaction_id):
            raise ValueError('Update transaction journal is invalid')
        install = Path(journal.install_dir).resolve(strict=False)
        candidate = Path(journal.candidate_dir).resolve(strict=False)
        backup = Path(journal.backup_dir).resolve(strict=False)
        health = Path(journal.health_marker).resolve(strict=False)
        expected_backup = install.parent / f'.{install.name}.backup-{journal.transaction_id}'
        if (
            candidate.parent != install.parent
            or backup != expected_backup.resolve(strict=False)
            or health.parent != staging
        ):
            raise ValueError('Update transaction paths failed ownership validation')
        if journal.stage in {UpdateTransactionStage.COMMITTED, UpdateTransactionStage.ROLLED_BACK}:
            return journal
        if journal.stage in {UpdateTransactionStage.PREPARED, UpdateTransactionStage.WAITING_FOR_EXIT}:
            return journal
        rolling = self._advance(path, journal, UpdateTransactionStage.ROLLING_BACK, error=journal.error or 'Recovered interrupted transaction')
        try:
            if install.exists() and backup.exists():
                if candidate.exists():
                    raise FileExistsError('Failed candidate path is already occupied')
                self.replace_path(install, candidate)
            if backup.exists() and not install.exists():
                self.replace_path(backup, install)
            if not install.is_dir():
                raise FileNotFoundError('Known-good installation could not be restored')
            return self._advance(path, rolling, UpdateTransactionStage.ROLLED_BACK, error=rolling.error)
        except BaseException as exc:
            self._advance(path, rolling, UpdateTransactionStage.ROLLBACK_FAILED, error=str(exc))
            raise RuntimeError('Interrupted update recovery failed; files were preserved') from exc

    def _rollback(self, path: Path, journal: UpdateTransactionJournal, install: Path, candidate: Path, backup: Path, cause: BaseException) -> None:
        rolling = self._advance(path, journal, UpdateTransactionStage.ROLLING_BACK, error=str(cause))
        try:
            if install.exists():
                if candidate.exists():
                    raise FileExistsError('Cannot preserve failed candidate during rollback')
                self.replace_path(install, candidate)
            if backup.exists():
                self.replace_path(backup, install)
            self._advance(path, rolling, UpdateTransactionStage.ROLLED_BACK, error=str(cause))
        except BaseException as rollback_error:
            self._advance(path, rolling, UpdateTransactionStage.ROLLBACK_FAILED, error=f'{cause}; rollback: {rollback_error}')
            raise RuntimeError('Update failed and rollback could not be completed') from rollback_error

    @staticmethod
    def _tree_size(root: Path) -> int:
        return sum(path.stat().st_size for path in root.rglob('*') if path.is_file())

    @staticmethod
    def _acquire_lock(path: Path) -> int:
        try:
            return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError('Another update transaction owns this staging directory') from exc

    @classmethod
    def _advance(cls, path: Path, journal: UpdateTransactionJournal, stage: UpdateTransactionStage, *, error: str = '') -> UpdateTransactionJournal:
        updated = UpdateTransactionJournal(journal.transaction_id, stage, journal.install_dir, journal.candidate_dir, journal.backup_dir, journal.health_marker, error)
        cls._save(path, updated)
        return updated

    @staticmethod
    def _save(path: Path, journal: UpdateTransactionJournal) -> None:
        temporary = path.with_suffix('.tmp')
        payload = asdict(journal)
        payload['stage'] = journal.stage.value
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)


def wait_for_process_exit(pid: int, timeout_seconds: int) -> bool:
    if pid <= 0:
        return True
    if sys.platform == 'win32':
        import ctypes
        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return True
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_seconds * 1000) == 0
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def launch_health_check(executable: Path, transaction_id: str, marker: Path):
    flags = 0x08000000 if sys.platform == 'win32' else 0
    isolated_data = marker.parent / 'offline-self-test-data'
    environment = os.environ.copy()
    environment['YT_DOWNLOADER_DATA_DIR'] = str(isolated_data)
    environment['YT_DOWNLOADER_VIDEOS_DIR'] = str(isolated_data / 'Videos')
    self_test = subprocess.run(
        [str(executable), '--self-test'], close_fds=True, creationflags=flags,
        cwd=executable.parent, env=environment, timeout=60,
    )
    if self_test.returncode != 0:
        raise RuntimeError('New version failed its isolated offline self-test')
    return subprocess.Popen(
        [str(executable), '--update-health-check', transaction_id, str(marker)],
        close_fds=True,
        creationflags=flags,
        cwd=executable.parent,
    )


def wait_for_health(marker: Path, process: object, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if marker.is_file():
            try:
                payload = json.loads(marker.read_text(encoding='utf-8'))
                return payload.get('status') == 'ok'
            except (OSError, json.JSONDecodeError):
                return False
        poll = getattr(process, 'poll', None)
        if callable(poll) and poll() is not None:
            return False
        time.sleep(0.05)
    return False


def terminate_launched_process(process: object) -> None:
    terminate = getattr(process, 'terminate', None)
    if callable(terminate):
        terminate()
    wait = getattr(process, 'wait', None)
    if callable(wait):
        try:
            wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            kill = getattr(process, 'kill', None)
            if callable(kill):
                kill()

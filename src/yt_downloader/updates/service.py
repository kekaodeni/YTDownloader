"""Qt-facing update state machine; blocking work always runs outside the GUI thread."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import threading
import time
import math
from typing import Callable
from semver import Version

from PySide6.QtCore import QObject, QThreadPool, Signal

from yt_downloader.core.errors import AppError, ErrorContext
from yt_downloader.core.errors import OperationCancelled
from yt_downloader.updates.models import (
    UpdateCapability, UpdateManifest, UpdateProgress, UpdateRelease, UpdateState, VerifiedUpdatePackage,
)
from yt_downloader.updates.state import UpdatePersistentState, UpdateStateStore
from yt_downloader.updates.protocol import compatible
from yt_downloader.workers.function_worker import FunctionWorker


class _ThreadPoolRunner:
    def start(self, worker: FunctionWorker) -> None:
        QThreadPool.globalInstance().start(worker)


class UpdateService(QObject):
    state_changed = Signal(object)
    update_available = Signal(object)
    up_to_date = Signal()
    progress = Signal(object)
    ready = Signal(object)
    cancelled = Signal()
    failed = Signal(object, bool)
    install_prepared = Signal(object)

    def __init__(
        self,
        *,
        current_version: str,
        discovery,
        fetch_bytes: Callable[[str], bytes],
        keyring,
        state_store: UpdateStateStore,
        downloader,
        staging_root: Path,
        capability: UpdateCapability,
        runner=None,
        now: Callable[[], datetime] | None = None,
        backup_size: Callable[[], int] | None = None,
        disk_margin: int = 64 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.current_version = current_version
        self.discovery = discovery
        self.fetch_bytes = fetch_bytes
        self.keyring = keyring
        self.state_store = state_store
        self.downloader = downloader
        self.staging_root = Path(staging_root)
        self.capability = capability
        self.runner = runner or _ThreadPoolRunner()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.backup_size = backup_size or (lambda: 0)
        self.disk_margin = disk_margin
        self.clock = clock
        self._download_started = 0.0
        self.state = UpdateState.IDLE
        self.check_manual = False
        self.last_operation = ''
        self.latest_progress: UpdateProgress | None = None
        self.manifest: UpdateManifest | None = None
        self.verified_package: VerifiedUpdatePackage | None = None
        self._raw_manifest = b''
        self._signature = b''
        self._cancel = threading.Event()
        self._workers: list[FunctionWorker] = []

    def check(self, *, manual: bool) -> bool:
        if self.verified_package is not None or self.state in {UpdateState.READY_TO_INSTALL, UpdateState.CHECKING, UpdateState.DOWNLOADING, UpdateState.CANCELLING, UpdateState.VERIFYING, UpdateState.PREPARING_INSTALL, UpdateState.PREPARING_EXIT, UpdateState.INSTALLING, UpdateState.ROLLING_BACK}:
            return False
        if not manual and not self.state_store.should_auto_check(self.now()):
            return False
        self.check_manual = manual
        self.last_operation = 'check'
        self.manifest = None
        self._raw_manifest = self._signature = b''
        self.latest_progress = None
        self._set_state(UpdateState.CHECKING)
        worker = FunctionWorker(self._check_worker)
        self._workers.append(worker)
        worker.signals.result.connect(lambda result: self._check_succeeded(result, manual))
        worker.signals.error.connect(lambda error: self._operation_failed(error, manual))
        worker.signals.finished.connect(lambda current=worker: self._worker_finished(current))
        self.runner.start(worker)
        return True

    def _check_worker(self):
        releases = self.discovery.check(self.current_version)
        if not releases:
            return None
        for release in releases:
            raw = self.fetch_bytes(release.manifest_url)
            signature = self.fetch_bytes(release.signature_url)
            manifest = self.keyring.verify(raw, signature, release)
            if not compatible(manifest, self.current_version, self.current_version):
                continue
            persisted = self.state_store.load()
            if persisted.highest_verified_version:
                if manifest.version < Version.parse(persisted.highest_verified_version):
                    raise ValueError('Verified update is older than the highest previously verified version')
            return manifest, raw, signature
        return UpdateState.NO_COMPATIBLE_UPDATE

    def _check_succeeded(self, result, manual: bool) -> None:
        checked = self.now().isoformat()
        if result is UpdateState.NO_COMPATIBLE_UPDATE:
            self._save_state(replace(self.state_store.load(), last_checked_at=checked, last_error=''))
            self._set_state(UpdateState.NO_COMPATIBLE_UPDATE)
            return
        if result is None:
            self._save_state(replace(self.state_store.load(), last_checked_at=checked, last_error=''))
            self._set_state(UpdateState.UP_TO_DATE)
            self.up_to_date.emit()
            return
        manifest, self._raw_manifest, self._signature = result
        self.manifest = manifest
        persisted = self.state_store.load()
        self._save_state(replace(
            persisted, last_checked_at=checked, last_error='',
            highest_verified_version=str(max(
                Version.parse(persisted.highest_verified_version or '0.0.0'),
                manifest.version,
            )),
        ))
        self._set_state(UpdateState.AVAILABLE)
        self.update_available.emit(manifest)

    def download(self) -> bool:
        if self.capability is UpdateCapability.CHECK_ONLY or self.manifest is None or self.downloader is None:
            return False
        if self.state not in {UpdateState.AVAILABLE, UpdateState.FAILED}:
            return False
        if self.state is UpdateState.FAILED and self.last_operation != 'download':
            return False
        self.last_operation = 'download'
        self.latest_progress = None
        self._download_started = self.clock()
        self._cancel = threading.Event()
        self._set_state(UpdateState.DOWNLOADING)
        worker = FunctionWorker(self._download_worker)
        self._workers.append(worker)
        worker.signals.result.connect(self._download_succeeded)
        worker.signals.cancelled.connect(self._download_cancelled)
        worker.signals.error.connect(lambda error: self._operation_failed(error, True))
        worker.signals.finished.connect(lambda current=worker: self._worker_finished(current))
        self.runner.start(worker)
        return True

    def _download_worker(self):
        try:
            verified = self.downloader.download(
                self.manifest, self.staging_root,
                self._report_progress, self._cancel,
                backup_size=self.backup_size(), margin=self.disk_margin,
                verification_callback=lambda: self._set_state(UpdateState.VERIFYING),
            )
        except Exception as exc:
            if self._cancel.is_set():
                raise OperationCancelled(ErrorContext(stage='Downloading update')) from exc
            raise
        transaction = verified.path.parent
        (transaction / 'update-manifest.json').write_bytes(self._raw_manifest)
        (transaction / 'update-manifest.sig').write_bytes(self._signature)
        return verified

    def _report_progress(self, values) -> None:
        downloaded, total = values
        elapsed = self.clock() - self._download_started
        speed = downloaded / elapsed if elapsed > 0 and downloaded > 0 else None
        if speed is not None and (not math.isfinite(speed) or speed <= 0):
            speed = None
        eta = max(0, total - downloaded) / speed if speed else None
        self.latest_progress = UpdateProgress(downloaded, total, speed, eta)
        self.progress.emit(self.latest_progress)

    def cancel(self) -> bool:
        if self.state is not UpdateState.DOWNLOADING:
            return False
        self._set_state(UpdateState.CANCELLING)
        self._cancel.set()
        cancel_current = getattr(self.downloader, 'cancel_current', None)
        if callable(cancel_current):
            cancel_current()
        return True

    def _download_succeeded(self, verified: VerifiedUpdatePackage) -> None:
        self.verified_package = verified
        self._save_state(replace(
            self.state_store.load(), transaction_id=verified.transaction_id,
            pending_version=str(verified.manifest.version),
        ))
        self._set_state(UpdateState.READY_TO_INSTALL)
        self.ready.emit(verified)

    def _download_cancelled(self) -> None:
        self._set_state(UpdateState.AVAILABLE if self.manifest else UpdateState.IDLE)
        self.cancelled.emit()

    def _operation_failed(self, error: AppError, manual: bool) -> None:
        self._save_state(replace(self.state_store.load(), last_checked_at=self.now().isoformat(), last_error=error.user_message))
        self._set_state(UpdateState.FAILED)
        self.failed.emit(error, manual)

    def _save_state(self, state: UpdatePersistentState) -> None:
        try:
            self.state_store.save(state)
        except OSError:
            pass

    def _set_state(self, state: UpdateState) -> None:
        self.state = state
        self.state_changed.emit(state)

    def _worker_finished(self, worker: FunctionWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def prepare_install_command(self, install_dir: Path, data_dir: Path, original_pid: int) -> tuple[str, ...] | None:
        if self.capability is not UpdateCapability.AUTO_INSTALL or self.verified_package is None:
            return None
        from yt_downloader.updates.installation import InstallRequest, prepare, checked_path
        install = checked_path(install_dir, exists=True)
        data = checked_path(data_dir)
        transaction = self.verified_package.path.parent.resolve(strict=True)
        if transaction.parent != self.staging_root.resolve(strict=True) or transaction.name != 'update-' + self.verified_package.transaction_id:
            raise ValueError('Stored update transaction identity changed')
        return prepare(InstallRequest(transaction, install, data, self.current_version,
                                      str(self.verified_package.manifest.version), original_pid), self.keyring)

    def prepare_install(self, install_dir: Path, data_dir: Path, original_pid: int) -> bool:
        retry = self.state is UpdateState.FAILED and self.last_operation == 'prepare' and self.verified_package is not None
        if (self.state is not UpdateState.READY_TO_INSTALL and not retry) or self.capability is not UpdateCapability.AUTO_INSTALL:
            return False
        self.last_operation = 'prepare'
        self._set_state(UpdateState.PREPARING_INSTALL)
        worker = FunctionWorker(lambda: self.prepare_install_command(install_dir, data_dir, original_pid))
        self._workers.append(worker)
        worker.signals.result.connect(self._install_prepared)
        worker.signals.error.connect(lambda error: self._operation_failed(error, True))
        worker.signals.finished.connect(lambda: self._worker_finished(worker))
        self.runner.start(worker)
        return True

    def _install_prepared(self, command) -> None:
        if command is None:
            self._operation_failed(AppError('update_prepare_failed', '无法准备更新，请重试。', 'No prepared updater command'), True)
            return
        self._set_state(UpdateState.PREPARING_EXIT)
        self.install_prepared.emit(command)

    def restore_verified_package(self) -> bool:
        if self.capability is UpdateCapability.CHECK_ONLY:
            return False
        persisted = self.state_store.load()
        if not persisted.transaction_id or not persisted.pending_version:
            return False
        try:
            version = Version.parse(persisted.pending_version)
            transaction = (self.staging_root / f'update-{persisted.transaction_id}').resolve(strict=True)
            if transaction.parent != self.staging_root.resolve(strict=True):
                raise ValueError('Stored update transaction escaped staging root')
            journal = transaction/'update-transaction.json'
            if journal.exists():
                raise ValueError('An attempted installation must be recovered, not installed again')
            raw = (transaction / 'update-manifest.json').read_bytes()
            signature = (transaction / 'update-manifest.sig').read_bytes()
            base = f'https://github.com/kekaodeni/YTDownloader/releases/download/v{version}/'
            release = UpdateRelease(
                version, f'v{version}', base + 'update-manifest.json',
                base + 'update-manifest.sig',
                f'https://github.com/kekaodeni/YTDownloader/releases/tag/v{version}',
            )
            manifest = self.keyring.verify(raw, signature, release)
            # A staged manifest is untrusted again after a restart.  Reapply
            # the same application/helper capability gate used by discovery
            # before exposing the package as installable.
            from yt_downloader.updates.protocol import compatible
            if not compatible(manifest, self.current_version, self.current_version):
                raise ValueError('Stored update protocol or minimum version is incompatible')
            package = transaction / manifest.package.name
            if package.stat().st_size != manifest.package.compressed_size:
                raise ValueError('Stored update package length changed')
            digest = hashlib.sha256()
            with package.open('rb') as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != manifest.package.sha256:
                raise ValueError('Stored update package hash changed')
            self.manifest = manifest
            self._raw_manifest = raw
            self._signature = signature
            self.verified_package = VerifiedUpdatePackage(persisted.transaction_id, package, manifest)
            self._set_state(UpdateState.READY_TO_INSTALL)
            return True
        except (OSError, ValueError, json.JSONDecodeError):
            self._save_state(replace(persisted, transaction_id='', pending_version=''))
            return False

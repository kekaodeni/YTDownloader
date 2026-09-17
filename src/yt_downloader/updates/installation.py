"""Shared, Qt-free transaction preparation and independent helper validation."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil

from semver import Version

from yt_downloader.updates.archive import SafePackageExtractor as Archive
from yt_downloader.updates.models import UpdateManifest, UpdateRelease
from yt_downloader.updates.protocol import HELPER_PATHS, compatible


def checked_path(path: Path, *, exists=False) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or Archive._is_reparse(part):
            raise ValueError('Update paths must not contain links or reparse points')
    return path.resolve(strict=exists)


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix('.tmp')
    with temporary.open('x', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def transaction_path(transaction: Path, data: Path) -> Path:
    transaction = checked_path(transaction, exists=True)
    data = checked_path(data)
    if transaction.parent != data / 'update-staging' or not re.fullmatch(r'update-[A-Za-z0-9][A-Za-z0-9._-]{0,120}', transaction.name):
        raise ValueError('Update transaction escaped owned staging')
    return transaction


def verify_package(transaction: Path, target: str, keyring) -> UpdateManifest:
    version = Version.parse(target)
    base = f'https://github.com/kekaodeni/YTDownloader/releases/download/v{version}/'
    release = UpdateRelease(version, f'v{version}', base+'update-manifest.json', base+'update-manifest.sig',
                            f'https://github.com/kekaodeni/YTDownloader/releases/tag/v{version}')
    for name in ('update-manifest.json', 'update-manifest.sig'):
        path = checked_path(transaction / name, exists=True)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Update metadata is too large')
    manifest = keyring.verify((transaction/'update-manifest.json').read_bytes(),
                             (transaction/'update-manifest.sig').read_bytes(), release)
    package = checked_path(transaction / manifest.package.name, exists=True)
    if package.stat().st_size != manifest.package.compressed_size:
        raise ValueError('Update package size changed after verification')
    if Archive.file_hash(package) != manifest.package.sha256:
        raise ValueError('Update package hash changed after verification')
    return manifest


@dataclass(frozen=True)
class InstallRequest:
    transaction: Path
    install: Path
    data: Path
    current_version: str
    target_version: str
    original_pid: int

    def validate_paths(self):
        transaction_path(self.transaction, self.data)
        install = checked_path(self.install)
        data = checked_path(self.data)
        if install.is_relative_to(data) or data.is_relative_to(install):
            raise ValueError('Application and user data directories overlap')
        if type(self.original_pid) is not int or self.original_pid <= 0:
            raise ValueError('Original process id must be positive')
        if Version.parse(self.target_version) <= Version.parse(self.current_version):
            raise ValueError('Target must be newer than installed version')

    def binding(self, manifest: UpdateManifest, helper_hash: str) -> dict:
        return dict(schema_version=1, transaction_id=self.transaction.name,
                    install_dir=str(self.install), data_dir=str(self.data), original_pid=self.original_pid,
                    current_version=self.current_version, target_version=self.target_version,
                    manifest_sha256=Archive.file_hash(self.transaction/'update-manifest.json'),
                    package_sha256=manifest.package.sha256, helper_sha256=helper_hash)


def prepare(request: InstallRequest, keyring) -> tuple[str, ...]:
    from yt_downloader.updates.transaction import InstallPreflight
    request.validate_paths()
    manifest = verify_package(request.transaction, request.target_version, keyring)
    if not compatible(manifest, request.current_version, request.current_version):
        raise ValueError('Update protocol or minimum version is incompatible')
    Archive.validate_tree(request.install, expected_version=request.current_version)
    info = Archive._load_json(request.install/'BUILD-INFO.json')
    if info.get('validation_only') is not False:
        raise ValueError('Validation builds cannot install updates')
    source = request.install / HELPER_PATHS[Archive.layout(info)]
    source_hash = Archive.file_hash(source)
    required = manifest.package.compressed_size + manifest.package.extracted_size + sum(
        path.stat().st_size for path in request.install.rglob('*') if path.is_file()) + 64 * 1024 * 1024
    InstallPreflight().validate(request.install, request.data, required_bytes=required)
    if (request.transaction/'update-transaction.json').exists():
        raise ValueError('Existing update transaction must be recovered first')
    destination = checked_path(request.transaction/'updater/YTDownloaderUpdater.exe')
    destination.parent.mkdir(exist_ok=True)
    shutil.copy2(source, destination)
    if Archive.file_hash(destination) != source_hash:
        raise ValueError('Staged helper hash mismatch')
    atomic_json(request.transaction/'install-request.json', request.binding(manifest, source_hash))
    return (str(destination), '--transaction-dir', str(request.transaction), '--install-dir', str(request.install),
            '--data-dir', str(request.data), '--original-pid', str(request.original_pid),
            '--current-version', request.current_version, '--target-version', request.target_version)


def validate_request(request: InstallRequest, keyring, *, executing_helper: Path, recovery=False) -> UpdateManifest:
    request.validate_paths()
    manifest = verify_package(request.transaction, request.target_version, keyring)
    source = request.install
    if recovery:
        backup = source.parent / f'.{source.name}.backup-{request.transaction.name}'
        if backup.is_dir():
            source = checked_path(backup, exists=True)
    Archive.validate_tree(source, expected_version=request.current_version)
    info = Archive._load_json(source/'BUILD-INFO.json')
    helper_hash = Archive.file_hash(source / HELPER_PATHS[Archive.layout(info)])
    binding = Archive._load_json(checked_path(request.transaction/'install-request.json', exists=True))
    if binding != request.binding(manifest, helper_hash):
        raise ValueError('Update request identity or hashes changed')
    expected_helper = request.transaction/'updater/YTDownloaderUpdater.exe'
    if checked_path(executing_helper, exists=True) != expected_helper or Archive.file_hash(executing_helper) != helper_hash:
        raise ValueError('Updater does not belong to this transaction')
    return manifest

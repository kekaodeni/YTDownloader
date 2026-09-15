"""External updater entry point. This process intentionally has no Qt dependency."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from semver import Version

from yt_downloader.updates.archive import SafePackageExtractor
from yt_downloader.updates.models import UpdateRelease
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.transaction import InstallPreflight, TransactionalInstaller
from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS


UPDATER_PROTOCOL = 1
REPOSITORY = 'kekaodeni/YTDownloader'


def validate_upgrade_versions(current_value: str, target_value: str) -> tuple[Version, Version]:
    current = Version.parse(current_value)
    target = Version.parse(target_value)
    if target <= current:
        raise ValueError('The signed update version must be newer than the installed version')
    return current, target


def _arguments(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description='Install a verified YTDownloader update')
    parser.add_argument('--transaction-dir', required=True, type=Path)
    parser.add_argument('--install-dir', required=True, type=Path)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--original-pid', required=True, type=int)
    parser.add_argument('--current-version', required=True)
    parser.add_argument('--target-version', required=True)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    if not PRODUCTION_TRUSTED_KEYS:
        raise RuntimeError('Production update trust is not enabled in this build')
    current, target = validate_upgrade_versions(args.current_version, args.target_version)
    transaction = args.transaction_dir.resolve(strict=True)
    raw_manifest = (transaction / 'update-manifest.json').read_bytes()
    signature = (transaction / 'update-manifest.sig').read_bytes()
    release = UpdateRelease(
        target,
        f'v{target}',
        f'https://github.com/{REPOSITORY}/releases/download/v{target}/update-manifest.json',
        f'https://github.com/{REPOSITORY}/releases/download/v{target}/update-manifest.sig',
        f'https://github.com/{REPOSITORY}/releases/tag/v{target}',
    )
    manifest = TrustedKeyring(PRODUCTION_TRUSTED_KEYS).verify(raw_manifest, signature, release)
    if manifest.updater_protocol != UPDATER_PROTOCOL or current < manifest.minimum_auto_update_version:
        raise RuntimeError('This updater protocol cannot safely install the selected version')
    package = transaction / manifest.package.name
    if package.stat().st_size != manifest.package.compressed_size:
        raise ValueError('Update package size changed after verification')
    if hashlib.sha256(package.read_bytes()).hexdigest() != manifest.package.sha256:
        raise ValueError('Update package hash changed after verification')
    install = args.install_dir.resolve(strict=True)
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

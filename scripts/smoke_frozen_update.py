"""Build and exercise an isolated, test-key-only frozen update transaction."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from verify_release_archive import verify
from yt_downloader.updates.archive import SafePackageExtractor
from yt_downloader.updates.signing import create_signed_release_assets


CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: int = 240) -> None:
    completed = subprocess.run(command, cwd=cwd, env=env, creationflags=CREATE_NO_WINDOW, timeout=timeout)
    if completed.returncode:
        raise RuntimeError(f'Command failed ({completed.returncode}): {command[0]}')


def _write_ownership(root: Path) -> None:
    records = []
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name != 'SHA256SUMS.json':
            records.append({
                'Path': path.relative_to(root).as_posix(),
                'SHA256': hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    (root / 'SHA256SUMS.json').write_text(json.dumps(records, indent=2), encoding='utf-8')


def _zip_tree(root: Path, output: Path) -> None:
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                archive.write(path, 'YTDownloader/' + path.relative_to(root).as_posix())


def _build_test_binaries(repo: Path, work: Path, public_key: bytes) -> tuple[Path, Path]:
    app_hook = work / 'test-app-version-hook.py'
    app_hook.write_text("import yt_downloader\nyt_downloader.__version__ = '0.4.1'\n", encoding='utf-8')
    updater_hook = work / 'test-updater-trust-hook.py'
    updater_hook.write_text(
        "from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS\n"
        f"PRODUCTION_TRUSTED_KEYS['test-frozen-e2e'] = bytes.fromhex('{public_key.hex()}')\n",
        encoding='utf-8',
    )
    app_spec = (repo / 'YTDownloader.spec').read_text(encoding='utf-8')
    app_spec = app_spec.replace(
        'root = Path(SPEC).resolve().parent',
        f'root = Path({str(repo)!r})',
    ).replace('runtime_hooks=[],', f'runtime_hooks=[{str(app_hook)!r}],', 1)
    app_spec_path = work / 'YTDownloaderTest.spec'
    app_spec_path.write_text(app_spec, encoding='utf-8')
    updater_spec = (repo / 'YTDownloaderUpdater.spec').read_text(encoding='utf-8')
    updater_spec = updater_spec.replace(
        'root = Path(SPEC).resolve().parent',
        f'root = Path({str(repo)!r})',
    ).replace('runtime_hooks=[],', f'runtime_hooks=[{str(updater_hook)!r}],', 1)
    updater_spec_path = work / 'YTDownloaderUpdaterTest.spec'
    updater_spec_path.write_text(updater_spec, encoding='utf-8')
    dist = work / 'frozen-dist'
    _run([
        sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
        '--workpath', str(work / 'build-app'), '--distpath', str(dist), str(app_spec_path),
    ], cwd=repo)
    _run([
        sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
        '--workpath', str(work / 'build-updater'), '--distpath', str(work / 'updater-dist'),
        str(updater_spec_path),
    ], cwd=repo)
    return dist / 'YTDownloader', work / 'updater-dist' / 'YTDownloaderUpdater.exe'


def run(baseline_zip: Path, work: Path) -> dict[str, object]:
    repo = Path(__file__).resolve().parents[1]
    baseline_zip = baseline_zip.resolve(strict=True)
    work = work.resolve(strict=False)
    if work.exists():
        resolved_repo = repo.resolve(strict=True)
        relative_work = work.relative_to(resolved_repo / '.tool-stage')
        if not relative_work.parts:
            raise ValueError('Refusing to remove the shared .tool-stage root')
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / 'TEST-ONLY.txt').write_text(
        'Ephemeral frozen updater test. Never publish these files or trust roots.\n', encoding='utf-8',
    )
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private_path = work / 'test-private-key.pem'
    private_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b'frozen-smoke-only'),
    ))
    candidate, test_updater = _build_test_binaries(repo, work, public)
    shutil.copy2(test_updater, candidate / 'YTDownloaderUpdater.exe')
    (candidate / 'BUILD-INFO.json').write_text(json.dumps({
        'app_version': '0.4.1', 'validation_only': False,
        'updater_protocol': 1, 'test_update_build': True,
    }, indent=2), encoding='utf-8')
    _write_ownership(candidate)
    SafePackageExtractor.validate_tree(candidate, expected_version='0.4.1')
    package_root = work / 'test-release-assets'
    package_root.mkdir()
    package = package_root / 'YTDownloader-0.4.1-win64.zip'
    _zip_tree(candidate, package)
    acceptance = verify(package, work / 'candidate-acceptance', work / 'candidate-acceptance.json')
    create_signed_release_assets(
        package=package, private_key_path=private_path, password=b'frozen-smoke-only',
        key_id='test-frozen-e2e', trusted_keys={'test-frozen-e2e': public},
        repo_root=package_root, version='0.4.1', minimum_auto_update_version='0.4.0',
        notes_zh_cn='仅用于冻结更新验收', notes_en='Frozen updater acceptance only',
        published_at='2026-09-04T00:00:00Z',
        acceptance_report_path=work / 'candidate-acceptance.json',
    )
    install = work / 'installed-app'
    with zipfile.ZipFile(baseline_zip) as archive:
        size = sum(item.file_size for item in archive.infolist() if not item.is_dir())
    SafePackageExtractor().extract(baseline_zip, install, signed_extracted_size=size, expected_version='0.4.0')
    staging = work / 'update-frozen-e2e'
    staging.mkdir()
    for name in (package.name, 'update-manifest.json', 'update-manifest.sig'):
        shutil.copy2(package_root / name, staging / name)
    external_updater = staging / 'YTDownloaderUpdater-test-only.exe'
    shutil.copy2(test_updater, external_updater)
    data = work / 'user-data'
    data.mkdir()
    (data / 'history.db').write_bytes(b'preserve-user-data')
    env = os.environ.copy()
    env['YT_DOWNLOADER_UPDATE_HEALTH_SMOKE_EXIT'] = '1'
    _run([
        str(external_updater), '--transaction-dir', str(staging),
        '--install-dir', str(install), '--data-dir', str(data),
        '--original-pid', '0', '--current-version', '0.4.0', '--target-version', '0.4.1',
    ], cwd=staging, env=env, timeout=180)
    journal = json.loads((staging / 'update-transaction.json').read_text(encoding='utf-8'))
    installed = json.loads((install / 'BUILD-INFO.json').read_text(encoding='utf-8-sig'))
    backup = Path(journal['backup_dir'])
    previous = json.loads((backup / 'BUILD-INFO.json').read_text(encoding='utf-8-sig'))
    if journal['stage'] != 'COMMITTED' or installed['app_version'] != '0.4.1' or previous['app_version'] != '0.4.0':
        raise RuntimeError('Frozen update transaction did not preserve the expected versions')
    if (data / 'history.db').read_bytes() != b'preserve-user-data':
        raise RuntimeError('Frozen update transaction changed user data')
    result = {
        'status': 'ok', 'from_version': '0.4.0', 'to_version': '0.4.1',
        'transaction_stage': journal['stage'], 'user_data_preserved': True,
        'candidate_acceptance_sha256': acceptance['package_sha256'],
        'test_key_only': True,
    }
    (work / 'frozen-update-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-zip', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.baseline_zip, args.work_dir), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

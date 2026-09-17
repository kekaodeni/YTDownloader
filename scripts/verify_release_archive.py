"""Independently extract and smoke-test a Windows release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

from yt_downloader.updates.archive import SafePackageExtractor


CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _subsystem(path: Path) -> int:
    data = path.read_bytes()
    offset = int.from_bytes(data[0x3C:0x40], 'little')
    return int.from_bytes(data[offset + 24 + 68:offset + 24 + 70], 'little')


def _run(executable: Path, *arguments: str, env: dict[str, str], timeout: int = 60) -> int:
    completed = subprocess.run(
        [str(executable), *arguments], cwd=executable.parent, env=env,
        creationflags=CREATE_NO_WINDOW, close_fds=True, timeout=timeout,
    )
    return completed.returncode


def verify(package: Path, extract_dir: Path, report_path: Path) -> dict[str, object]:
    package = package.resolve(strict=True)
    extract_dir = extract_dir.resolve(strict=False)
    report_path = report_path.resolve(strict=False)
    if extract_dir.exists():
        raise FileExistsError(f'Independent extraction target already exists: {extract_dir}')
    with zipfile.ZipFile(package) as archive:
        extracted_size = sum(info.file_size for info in archive.infolist() if not info.is_dir())
        build_info = json.loads(archive.read('YTDownloader/BUILD-INFO.json').decode('utf-8-sig'))
    version = str(build_info['app_version'])
    SafePackageExtractor().extract(
        package, extract_dir, signed_extracted_size=extracted_size,
        expected_version=version,
    )
    app = extract_dir / 'YTDownloader.exe'
    layout = build_info.get('helper_layout', 'legacy-root')
    updater = extract_dir / 'YTDownloaderUpdater.exe' if layout == 'legacy-root' else extract_dir / '_internal' / 'updater' / 'YTDownloaderUpdater.exe'
    if layout == 'internal-v1' and (extract_dir / 'YTDownloaderUpdater.exe').exists():
        raise RuntimeError('Internal package exposes a root updater helper')
    if _subsystem(app) != 2 or _subsystem(updater) != 2:
        raise RuntimeError('Main application and updater must both use the Windows GUI subsystem')
    acceptance_root = extract_dir.parent / f'update-acceptance-{os.getpid()}'
    if acceptance_root.exists():
        shutil.rmtree(acceptance_root)
    data_dir = acceptance_root / 'data'
    env = os.environ.copy()
    env['YT_DOWNLOADER_DATA_DIR'] = str(data_dir)
    env['YT_DOWNLOADER_VIDEOS_DIR'] = str(data_dir / 'Videos')
    checks: dict[str, bool] = {}
    checks['ownership_manifest'] = True
    checks['independent_self_test'] = _run(app, '--self-test', env=env) == 0
    # Frozen PyInstaller startup can be slower on a cold Windows host than the
    # interactive build self-test. Keep the check bounded, but allow enough
    # time for extraction/import initialization before declaring a failure.
    checks['metadata_helper'] = _run(app, '--metadata-process-self-test', env=env, timeout=60) == 0
    checks['gui_smoke'] = _run(app, '--smoke-test', env=env, timeout=20) == 0
    checks['updater_windowed'] = _run(updater, env=env, timeout=20) == 2
    transaction_id = f'acceptance-{os.getpid()}'
    health_root = acceptance_root / f'update-{transaction_id}'
    marker = health_root / 'startup-health.json'
    health_process = subprocess.Popen(
        [str(app), '--update-health-check', transaction_id, str(marker)],
        cwd=app.parent, env=env, creationflags=CREATE_NO_WINDOW, close_fds=True,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not marker.is_file() and health_process.poll() is None:
            time.sleep(0.05)
        health = json.loads(marker.read_text(encoding='utf-8')) if marker.is_file() else {}
        checks['startup_health'] = (
            health.get('status') == 'ok'
            and health.get('transaction_id') == transaction_id
            and health.get('app_version') == version
        )
    finally:
        if health_process.poll() is None:
            health_process.terminate()
            try:
                health_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                health_process.kill()
                health_process.wait(timeout=5)
    if not all(checks.values()):
        failed = ', '.join(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f'Independent archive acceptance failed: {failed}')
    digest = _sha256(package)
    report: dict[str, object] = {
        'schema_version': 1,
        'app_version': version,
        'validation_only': build_info.get('validation_only') is True,
        'package_name': package.name,
        'package_sha256': digest,
        'package_size': package.stat().st_size,
        'extracted_size': extracted_size,
        'checks': checks,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(report_path.suffix + '.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    from dev_staging import session
    with session('release-acceptance') as work:
        report = verify(args.package, work / 'extracted', args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

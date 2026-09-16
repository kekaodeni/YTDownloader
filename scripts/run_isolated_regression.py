"""Run existing pytest cases without Windows Shell integration or user data.

Usage: .venv/Scripts/python.exe -B scripts/run_isolated_regression.py RUN_NAME [pytest args]
Every invocation owns a temporary session outside the checkout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def run(output):
    root = Path(__file__).resolve().parents[1]
    name = sys.argv[1]
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
        raise SystemExit('Use an alphanumeric run name with hyphens or underscores.')
    for key, folder in {
        'YT_DOWNLOADER_DATA_DIR': 'data', 'YT_DOWNLOADER_VIDEOS_DIR': 'videos',
        'LOCALAPPDATA': 'local', 'APPDATA': 'roaming', 'TEMP': 'temp', 'TMP': 'temp',
        'PYINSTALLER_CONFIG_DIR': 'pyinstaller',
    }.items():
        target = output / folder
        target.mkdir(exist_ok=True)
        os.environ[key] = str(target)
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QT_QUICK_BACKEND'] = 'software'
    os.environ['QML_DISABLE_DISK_CACHE'] = '1'
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'src'))
    os.chdir(root)

    blocked = {}
    def audit(event, args):
        if event.startswith('winreg.') or event.startswith('os.startfile'):
            blocked[event] = blocked.get(event, 0) + 1
            raise PermissionError(f'Forbidden Windows integration during isolated tests: {event}')
        if event == 'subprocess.Popen':
            command = str(args[0]).lower()
            if any(word in command for word in ('explorer', 'icaros', 'regsvr32', 'reg.exe')):
                raise RuntimeError(f'Forbidden Windows integration process: {command}')
    sys.addaudithook(audit)

    from yt_downloader.infrastructure import windows_thumbnail
    calls = {'thumbnail_checks': 0, 'shell_notifications': 0}
    def unavailable(*_args, **_kwargs):
        calls['thumbnail_checks'] += 1
        return None
    def no_notification(*_args, **_kwargs):
        calls['shell_notifications'] += 1
    windows_thumbnail.shell_thumbnail_matches = unavailable
    windows_thumbnail._shell_image = unavailable
    windows_thumbnail.notify_shell_updated = no_notification

    import pytest
    args = ['-p', 'pytestqt.plugin', '-p', 'no:cacheprovider',
            '--basetemp', str(output / 'pytest'),
            '--junitxml', str(output / 'results.xml'), *sys.argv[2:]]
    print('MANUAL VERIFICATION REQUIRED: Windows Shell/Explorer thumbnail checks and notifications are disabled.', flush=True)
    result = pytest.main(args)
    (output / 'isolation.json').write_text(json.dumps({
        'exit_code': int(result), 'pytest_args': args, 'shell_calls_omitted': calls,
        'blocked_windows_access': blocked,
        'desktop_status': 'MANUAL VERIFICATION REQUIRED',
        'qt_platform': 'offscreen', 'qt_backend': 'software',
        'assertions_modified': False,
    }, indent=2), encoding='utf-8')
    return result


def main():
    from dev_staging import session
    with session('regression') as output:
        result = run(output)
        if result:
            raise SystemExit(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

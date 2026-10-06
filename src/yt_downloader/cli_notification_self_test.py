"""Opt-in native notification verification for an isolated frozen build."""
import json
from pathlib import Path
import sys
from yt_downloader.infrastructure.runtime import resource_path
from yt_downloader.infrastructure.windows_notifications import send_windows_toast


def main():
    index = sys.argv.index('--notification-self-test')
    output = Path(sys.argv[index + 1])
    result = send_windows_toast('YTDownloader', 'Windows notification verification', resource_path('assets', 'app-icon.png'))
    result['frozen'] = bool(getattr(sys, 'frozen', False))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result.get('in_history') else 2

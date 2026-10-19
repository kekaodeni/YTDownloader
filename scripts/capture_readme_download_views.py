"""Render sanitized Download page screenshots for the project README."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from yt_downloader import __version__
from yt_downloader.core.models import AppSettings
from yt_downloader.services.media_resolver import MediaResolver
from yt_downloader.services.network_policy import NetworkPolicy
from yt_downloader.ui.quick_window import MainWindow

try:
    from scripts.verify_quick_ui import wait
except ModuleNotFoundError:
    from verify_quick_ui import wait


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('docs/images'))
    parser.add_argument('--report', type=Path)
    parser.add_argument('--url', default='https://www.youtube.com/watch?v=aqz-KE-bpKQ')
    parser.add_argument('--proxy-url', default='')
    parser.add_argument('--data-dir', type=Path, default=Path('artifacts/readme-capture-data'))
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    os.environ['YT_DOWNLOADER_DATA_DIR'] = str(data)
    os.environ['YT_DOWNLOADER_VIDEOS_DIR'] = str(data / 'Videos')
    network = NetworkPolicy('custom', args.proxy_url) if args.proxy_url else NetworkPolicy('system')
    video = MediaResolver(network_policy=network).fetch_metadata(args.url, threading.Event())

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(
        AppSettings(download_directory=r'D:\Videos', auto_check_updates=False, use_cookies=False),
        ytdlp_version='2026.8.19',
        ffmpeg_description='随软件提供',
    )
    from PySide6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen().availableGeometry()
    window.root.resize(min(1360, screen.width() - 20), min(900, screen.height() - 40))
    window.download_page.setField('directory', r'D:\Videos')
    window.download_page.setField('url', video.url)
    window.download_page.show_video(video)

    captures: dict[str, str] = {}

    def capture() -> None:
        for mode, filename in (
            ('light', f'v{__version__}-download-light.png'),
            ('dark', f'v{__version__}-download-dark.png'),
        ):
            window.theme.set_mode(mode)
            window.root.update()
            wait(350)
            assert window.theme.state['dark'] == (mode == 'dark')
            target = args.output_dir / filename
            if not window.grab().save(str(target), 'PNG'):
                raise RuntimeError(f'Qt Quick could not save {target}')
            captures[mode] = target.name
        warnings = list(window.qml_warnings)
        report = {
            'source': 'Final-version Qt Quick runtime, live public metadata, isolated data, neutral output path',
            'app_version': __version__,
            'source_url': args.url,
            'media_id': video.video_id,
            'page': 'download',
            'device_pixel_ratio': window.root.devicePixelRatio(),
            'logical_size': [window.root.width(), window.root.height()],
            'screenshots': captures,
            'qml_warnings': warnings,
        }
        from PySide6.QtCore import QObject
        visible = [str(item.property('text') or '') for item in window.root.findChildren(QObject)
                   if hasattr(item, 'isVisible') and item.isVisible()]
        private_markers = ['C:\\Users\\', 'C:/Users/', str(data), os.environ.get('USERNAME', '')]
        assert not any(marker and marker in text for marker in private_markers for text in visible), 'Private text in screenshot'
        if args.report:
            args.report.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.update(allowClose=True)
        window.close()
        window.dispose()
        app.processEvents()
        print(json.dumps(report, ensure_ascii=False))
        app.exit(1 if warnings else 0)

    window.show()
    window.root.raise_()
    window.root.requestActivate()
    QTimer.singleShot(800, capture)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

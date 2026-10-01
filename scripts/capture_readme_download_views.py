"""Render sanitized Download page screenshots for the project README."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, DownloadProgress, DownloadRequest, TaskStatus
from yt_downloader.ui.quick_window import MainWindow

try:
    from scripts.verify_quick_ui import sample_video, wait
except ModuleNotFoundError:
    from verify_quick_ui import sample_video, wait


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('docs/images'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(
        AppSettings(download_directory=r'D:\Videos', auto_check_updates=False),
        ytdlp_version='2026.8.19',
        ffmpeg_description='随软件提供',
    )
    window.root.resize(1440, 1200)
    window.download_page.setField('directory', r'D:\Videos')
    video = replace(
        sample_video(),
        video_id='readme-showcase',
        url='https://example.org/video/coastal-sunrise',
        title='Coastal Sunrise · A UHD Nature Film',
        channel='YTDownloader Sample Channel',
        duration=766,
        extractor_key='Youtube',
        metadata_compatibility='VERIFIED',
        download_compatibility='VERIFIED',
    )
    window.download_page.setField('url', video.url)
    window.download_page.show_video(video)
    request = DownloadRequest(
        'readme-showcase-task', video, video.formats[0], Path(r'D:\Videos'), video.title,
    )
    window.download_page.add_task(request)
    window.download_page.update_task(DownloadProgress(
        request.task_id, TaskStatus.DOWNLOADING_VIDEO, 67,
        67_000_000, 100_000_000, 8_700_000, 4,
    ))

    captures: dict[str, str] = {}

    def capture() -> None:
        for mode, filename in (
            ('light', 'v0.6.0-download-light.png'),
            ('dark', 'v0.6.0-download-dark.png'),
        ):
            window.theme.set_mode(mode)
            window.root.update()
            wait(350)
            target = args.output_dir / filename
            if not window.grab().save(str(target), 'PNG'):
                raise RuntimeError(f'Qt Quick could not save {target}')
            captures[mode] = str(target)
        warnings = list(window.qml_warnings)
        report = {
            'source': 'Qt Quick application render with offline controlled fixture',
            'page': 'download',
            'device_pixel_ratio': window.root.devicePixelRatio(),
            'logical_size': [window.root.width(), window.root.height()],
            'screenshots': captures,
            'qml_warnings': warnings,
        }
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

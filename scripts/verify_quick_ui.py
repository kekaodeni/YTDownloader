"""Offline visual/interaction verification for the real Qt Quick application."""
from __future__ import annotations
import argparse
from dataclasses import replace
from pathlib import Path
import json
import sys
import time

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QPoint, QTimer, Qt, QEventLoop
from PySide6.QtGui import QImage, QColor, QPainter, QLinearGradient
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, DownloadProgress, DownloadRequest, FormatOption, HistoryRecord, ParseState, TaskStatus, VideoInfo
from yt_downloader.core.errors import AppError
from yt_downloader.ui.quick_window import MainWindow
from yt_downloader.ui.quick_dialogs import ErrorSession

def sample_video():
    img = QImage(720, 405, QImage.Format.Format_RGB32)
    painter = QPainter(img)
    gradient = QLinearGradient(0, 0, 720, 405)
    gradient.setColorAt(0, QColor('#224B70'))
    gradient.setColorAt(1, QColor('#77A9BA'))
    painter.fillRect(img.rect(), gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#F2D7A4'))
    painter.drawEllipse(470, 65, 95, 95)
    painter.setBrush(QColor('#193C57'))
    painter.drawEllipse(-100, 230, 950, 360)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buffer, 'PNG')
    option = FormatOption('1080p', 1080, 30, 'avc1', 'mp4a', 'MP4', 'mp4', '137+140', 100_000_000, True, '137', '140', True)
    return VideoInfo('preview00001', 'https://www.youtube.com/watch?v=preview00001',
                     '海岸线 · 日出与海风 / Coastline', '界面验收样例', 766, None, bytes(data), (option,))

def wait(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--motion-seconds', type=int, default=0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(download_directory='D:/Videos', auto_check_updates=False),
                        ytdlp_version='2026.8.19', ffmpeg_description='随软件提供')
    window.show()
    window.root.raise_()
    window.root.requestActivate()
    video = sample_video()
    window.download_page.show_video(video)
    request = DownloadRequest('visual-task', video, video.formats[0], Path('D:/Videos'), video.title)
    window.download_page.add_task(request)
    window.download_page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 67, 67_000_000, 100_000_000, 8_700_000, 4))
    records = [HistoryRecord(f'h-{i}', video.video_id, video.url, video.title + f' · {i + 1}', Path('D:/Videos/example.mp4'), '1080p', 100_000_000, None, TaskStatus.COMPLETED, '2026-09-05 09:00') for i in range(500)]
    window.history_page.set_records(records)
    samples = []
    result = {}
    def steps():
        yield 600
        for theme in ('light', 'dark'):
            window.theme.set_mode(theme)
            for width, height in ((1200, 800), (820, 650), (500, 560)):
                window.root.resize(width, height)
                for index, name in enumerate(('download', 'history', 'settings', 'about')):
                    window._select_page(index)
                    if index == 0:
                        window.scroll_download_to_top()
                    window.root.raise_()
                    window.root.requestActivate()
                    window.root.update()
                    yield 400
                    for attempt in range(20):
                        host = window.root.findChild(QObject, f'pageHost-{index}')
                        if host.opacity() >= .999:
                            break
                        window.root.update()
                        yield 100
                    else:
                        raise RuntimeError(f'Page {index} animation did not settle; window may be occluded')
                    if index == 0:
                        window.scroll_download_to_top()
                    yield 100
                    path = args.output / f'{name}-{theme}-{width}.png'
                    window.grab().save(str(path))
                    samples.append(str(path))
        window.root.resize(1200, 800)
        window._select_page(1)
        window.history_page.select('h-0')
        for mode in ('light', 'dark'):
            window.theme.set_mode(mode)
            window.root.findChild(QObject, 'historyList').forceActiveFocus()
            QTest.keyClick(window.root, Qt.Key_F10, Qt.ShiftModifier)
            yield 400
            menu = window.root.findChild(QObject, 'historyMenu')
            assert menu.property('opened') and not menu.property('dim')
            path = args.output / f'history-menu-{mode}.png'
            window.grab().save(str(path))
            samples.append(str(path))
            QTest.keyClick(window.root, Qt.Key_Escape)
            yield 200
        window.root.resize(1200, 800)
        window._select_page(0)
        yield 400
        dialog = ErrorSession(AppError('test', '无法获取该视频的信息，可以重试。', 'Offline visual validation'), 'Redacted test report', window, retry_callback=lambda: None)
        dialog.show()
        yield 400
        window.grab().save(str(args.output / 'error-dialog-dark.png'))
        dialog.reject()
        yield 220
        result.update(screenshots=len(samples) + 1, qml_warnings=window.qml_warnings,
                      screen_hz=window.root.screen().refreshRate(), dpr=window.root.devicePixelRatio(),
                      graphics_api=str(window.root.rendererInterface().graphicsApi()))
        if args.motion_seconds:
            from yt_downloader.ui.quick_diagnostics import MotionProbe
            probe = MotionProbe(window)
            probe.start()
            yield args.motion_seconds * 1000
            result['motion'] = probe.stop()
        (args.output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = json.loads(json.dumps(result))
        summary.get('motion', {}).pop('raw_intervals_ms', None)
        print(json.dumps(summary, ensure_ascii=False))
        window.update(allowClose=True)
        window.close()
        app.quit()
    iterator = steps()
    def advance():
        try:
            delay = next(iterator)
        except StopIteration:
            return
        except BaseException:
            import traceback
            traceback.print_exc()
            app.exit(2)
            return
        QTimer.singleShot(delay, advance)
    QTimer.singleShot(0, advance)
    if app.exec():
        return 2
    window.dispose()
    return 1 if result['qml_warnings'] else 0

if __name__ == '__main__':
    raise SystemExit(main())

"""Real local media validation for menu hover, history covers and portrait preview."""
import argparse
from pathlib import Path
import json
from PySide6.QtCore import QObject, QTimer, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yt_downloader.core.models import AppSettings, HistoryRecord, TaskStatus
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.ui.quick_window import MainWindow
from yt_downloader.ui.quick_cover import CoverSession
from record_quick_ui import find


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1200)
    parser.add_argument('--height', type=int, default=800)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    service = FfmpegService(shell_thumbnail_checker=lambda *_: True)
    media = []
    for name, size in [('portrait', '240x426'), ('landscape', '426x240')]:
        path = output / f'{name}.mp4'
        service._run([str(service.ffmpeg_path), '-hide_banner', '-loglevel', 'error', '-y',
                      '-f', 'lavfi', '-i', f'testsrc2=s={size}:d=3:r=24',
                      '-f', 'lavfi', '-i', 'sine=duration=3', '-shortest', '-c:v', 'libx264',
                      '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path)])
        media.append(path)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(download_directory=str(output), auto_check_updates=False),
                        ytdlp_version='local validation', ffmpeg_description='随软件提供')
    page = window.history_page
    page.configure_thumbnails(service, output / 'history-cache')
    page.set_records([HistoryRecord(str(i), f'local-{i}', 'https://example.invalid',
                      '竖屏视频 · 完整封面' if i == 0 else '横屏视频 · 完整封面', path,
                      '1080p', path.stat().st_size, None, TaskStatus.COMPLETED, '2026-09-06')
                      for i, path in enumerate(media)])
    window.root.resize(args.width, args.height)
    window.show()
    window.root.raise_()
    window.root.requestActivate()
    window._select_page(1)
    captures = []
    def snap(name):
        path = output / f'{name}.png'
        window.grab().save(str(path))
        captures.append(path.name)
    def steps():
        yield 500
        for _ in range(100):
            if all(row['thumbnail'] for row in page.model.rows):
                break
            yield 100
        else:
            raise RuntimeError('History did not display extracted video covers')
        page.select('0')
        for theme in ('light', 'dark'):
            window.theme.set_mode(theme)
            yield 300
            snap('history-covers-' + theme)
            find(window, 'historyList').forceActiveFocus()
            QTest.keyClick(window.root, Qt.Key_F10, Qt.ShiftModifier)
            yield 250
            menu = find(window, 'historyMenu')
            highlights = [x for x in menu.findChildren(QObject) if x.objectName().startswith('menuHighlight-')]
            for index, label in enumerate(('打开文件夹', '复制链接', '重新下载')):
                target = next(x for x in highlights if x.objectName() == 'menuHighlight-' + label)
                QTest.mouseMove(window.root, target.mapToScene(QPointF(target.width()/2, target.height()/2)).toPoint())
                yield 35
                assert sum(x.opacity() > 0 for x in highlights) == 1
                snap(f'menu-{theme}-{index}')
            QTest.keyClick(window.root, Qt.Key_Escape)
            yield 200
            for index, path in enumerate(media):
                session = CoverSession(path, f'local-{index}', output/'previews', service, window)
                session.thumbnail_set.connect(lambda result, task=str(index): page.invalidate_thumbnail(task))
                session.show()
                for _ in range(100):
                    if session.state['previewEnabled']:
                        break
                    yield 100
                session.setTimestamp(1)
                session.generatePreview()
                for _ in range(100):
                    if session.state['applyEnabled']:
                        break
                    yield 100
                assert session.state['applyEnabled']
                yield 400
                preview = find(window, 'coverPreview')
                assert abs(preview.width()/preview.height()-session.state['previewRatio']) < .001
                ancestor = preview.parentItem()
                while ancestor:
                    if ancestor.clip():
                        origin = preview.mapToItem(ancestor, QPointF(0, 0))
                        assert origin.y() >= -.5 and origin.y() + preview.height() <= ancestor.height() + .5, 'Preview is clipped vertically'
                    ancestor = ancestor.parentItem()
                snap(f'cover-{path.stem}-{theme}')
                if theme == 'light' and index == 0:
                    old = page.model.get(0)['thumbnail']
                    session.apply()
                    for _ in range(100):
                        if session.state['completed'] and page.model.get(0)['thumbnail'] != old:
                            break
                        yield 100
                    assert session.state['completed'] and page.model.get(0)['thumbnail'] != old
                session.reject()
                yield 300
        assert not window.qml_warnings
        (output/'verification.json').write_text(json.dumps(dict(screenshots=captures, qml_warnings=window.qml_warnings,
            history_covers=True, embedded_cover_refresh=True, portrait_fit=True, single_menu_highlight=True), indent=2), encoding='utf-8')
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
    try:
        return app.exec()
    finally:
        for session in tuple(window.dialogs.sessions):
            session.reject()
        window.dispose()


if __name__ == '__main__':
    raise SystemExit(main())

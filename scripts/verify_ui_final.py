"""Offline, real Qt Quick acceptance captures for shared navigation and popups.

Uses isolated settings and media fixtures; never writes the user's configuration.
Recordings retain actual capture timestamps, with PNG compression off the GUI thread.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtQml import QQmlProperty
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yt_downloader.core.models import AppSettings, DownloadRequest, HistoryRecord, TaskStatus
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.media_metadata import resolve_metadata
from yt_downloader.ui.quick_window import MainWindow
from scripts.verify_i18n_features_ui import find, wait
from scripts.verify_quick_ui import sample_video


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-dpr', required=True, type=float)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow(AppSettings(download_directory=str(args.output), auto_check_updates=False),
                   ytdlp_version='offline fixture', ffmpeg_description='')
    w.settings_page.save_requested.connect(w.settings_page.mark_saved)
    w.root.resize(1200, 800)
    w.show()
    w.root.raise_()
    w.root.requestActivate()
    wait(350)
    assert abs(w.root.devicePixelRatio() - args.expected_dpr) < .02
    pictures, clips, cases = [], [], []

    def click(item, button=Qt.LeftButton):
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
        QTest.mouseMove(w.root, point)
        QTest.mouseClick(w.root, button, Qt.NoModifier, point)

    def snap(name):
        path = args.output / (name + '.png')
        assert w.grab().save(str(path))
        pictures.append(str(path))

    def descendants(item):
        for child in item.childItems():
            yield child
            yield from descendants(child)

    def bar_for(item):
        direct = [child for child in item.childItems() if child.inherits('QQuickScrollBar')]
        return direct[0] if direct else next(child for child in descendants(item) if child.inherits('QQuickScrollBar'))

    def history_border():
        values = [QQmlProperty(find(w, f'history-h-{i}'), 'border.width').read() for i in range(3)]
        assert values == [1, 1, 1], values
        assert w.history_page.state['checkedCount'] == 3
        return values

    def record(name, actions, selection=False):
        folder = args.output / name
        folder.mkdir(exist_ok=True)
        frames, futures = [], []
        writer = ThreadPoolExecutor(max_workers=2) if args.record else None
        started = time.perf_counter()
        def capture():
            picture = w.grab()
            data = {'at': time.perf_counter() - started}
            if selection:
                data['outlines'] = history_border()
            else:
                data['mainY'] = find(w, 'mainNavigation-selection').y()
                data['settingsY'] = find(w, 'settingsNavigation-selection').y()
            if writer:
                futures.append(writer.submit(picture.save, str(folder/f'frame-{len(frames):04d}.png')))
            frames.append(data)
        capture()
        timer = QTimer()
        timer.timeout.connect(capture)
        timer.start(16)
        try:
            for action in actions:
                action()
                wait(450)
        finally:
            timer.stop()
            if writer:
                writer.shutdown(wait=True)
        assert all(f.result() for f in futures)
        (folder/'frames.json').write_text(json.dumps(frames, indent=2), encoding='utf-8')
        if args.record:
            manifest = ['ffconcat version 1.0']
            for i, frame in enumerate(frames):
                duration = frames[i+1]['at']-frame['at'] if i+1 < len(frames) else 1/60
                manifest.extend([f"file 'frame-{i:04d}.png'", 'option framerate 60', f'duration {duration:.6f}'])
            concat = folder/'frames.ffconcat'
            concat.write_text('\n'.join(manifest), encoding='utf-8')
            subprocess.run([str(FfmpegService().ffmpeg_path), '-hide_banner', '-loglevel', 'error', '-y',
                            '-f', 'concat', '-safe', '0', '-i', str(concat), '-vf', 'scale=1200:800',
                            '-fps_mode', 'vfr', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19',
                            '-pix_fmt', 'yuv420p', str(args.output/(name+'.mp4'))], check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            clips.append(str(args.output/(name+'.mp4')))

    media = sample_video()
    for theme in ('light', 'dark'):
        w.theme.set_mode(theme)
        w._select_page(0)
        wait(250)
        record(theme+'-navigation', [lambda n=n: click(find(w, f'nav-{n}')) for n in (1, 3, 0, 2)] +
               [lambda n=n: click(find(w, f'settingsNav-{n}')) for n in (1, 2, 3, 4, 5, 0)])
        for category, name in enumerate(('appearance', 'download', 'cookies', 'network', 'update', 'tools')):
            QTest.mouseMove(w.root, QPointF(0, 0).toPoint())
            w.settings_page.selectCategory(category)
            wait(260)
            surface = find(w, 'settingsNavigation-selection')
            assert QQmlProperty(surface, 'border.width').read() == 0
            scroll = find(w, 'settingsScroll')
            bar = bar_for(scroll)
            assert bar.width() == 12
            assert bar.isVisible() == (scroll.property('contentHeight') > scroll.height())
            snap(theme+'-settings-'+name)
            cases.append([theme, name, 'shared navigation / scrollbar'])

        w.settings_page.selectCategory(0)
        w.settings_page.setSetting('language', 'th-TH')
        wait(260)
        combo = find(w, 'languageCombo')
        click(combo)
        wait(200)
        view = find(w, 'options-languageCombo')
        old_y, old_names = view.property('contentY'), combo.property('model')
        for y in (1, 10, 200, 40, 220, 1):
            QTest.mouseMove(w.root, view.mapToScene(QPointF(30, y)).toPoint())
            wait(30)
            assert view.property('contentY') == old_y
            assert combo.property('model') == old_names
        compact = bar_for(view)
        assert compact.property('compact') and compact.width() == 12
        snap(theme+'-language-popup-compact-scrollbar')
        QTest.keyClick(w.root, Qt.Key_Escape)
        wait(200)
        w.settings_page.setSetting('language', 'zh-CN')
        w.settings_page.selectCategory(1)
        wait(250)
        scroll = find(w, 'settingsScroll')
        bar = bar_for(scroll)
        QTest.mouseMove(w.root, QPointF(0, 0).toPoint())
        wait(1100)
        assert bar.property('thumbWidth') == 4
        snap(theme+'-scrollbar-idle')
        content_width = find(w, 'settingsCategory-1').width()
        QTest.mouseMove(w.root, bar.mapToScene(QPointF(6, bar.height()/2)).toPoint())
        for _ in range(4):
            wait(60)
            w.grab()
        assert abs(bar.property('thumbWidth') - 6) < .01, (theme, bar.property('hovered'), bar.property('thumbWidth'), bar.isVisible(), bar.mapToScene(QPointF(6, bar.height()/2)))
        assert find(w, 'settingsCategory-1').width() == content_width
        snap(theme+'-scrollbar-hover')
        w.settings_page.newProfile()
        wait(240)
        assert bar_for(find(w, 'profileEditorBody')).width() == 12
        w.settings_page.closeProfileEditor()
        wait(200)

        w.history_page.set_records([HistoryRecord(f'h-{i}', media.video_id, media.url,
            f'历史记录 {i+1} · 选择状态与键盘焦点独立', args.output/'example.mp4', '1080p',
            123456789, None, TaskStatus.COMPLETED, '2026-09-30 12:00') for i in range(20)])
        w._select_page(1)
        w.history_page.manage(True)
        for i in range(3):
            w.history_page.toggle(f'h-{i}')
        wait(260)
        def menu():
            click(find(w, 'history-h-0'), Qt.RightButton)
            wait(180)
            snap(theme+'-history-selected-menu')
        def confirm():
            click(find(w, 'historyContextDelete'))
            wait(220)
            assert find(w, 'dialog-confirm').property('visible')
            snap(theme+'-history-confirm')
        def cancel():
            QTest.keyClick(w.root, Qt.Key_Escape)
        record(theme+'-history-popup-lifecycle', [menu, confirm, cancel], selection=True)
        history_border()
        snap(theme+'-history-cancelled')
        cases.append([theme, 'history', 'selection outline constant in every captured frame'])
        w.history_page.manage(False)

        w._select_page(0)
        for i in range(8):
            w.download_page.add_task(DownloadRequest(f'{theme}-task-{i}', media, media.formats[0], args.output, 'UI fixture'))
        wait(260)
        assert bar_for(find(w, 'taskList')).isVisible()
        snap(theme+'-download-tasks-scrollbar')
        collection = resolve_metadata({'_type': 'playlist', 'title': 'Playlist · UI fixture',
            'entries': [{'id': str(i), 'title': f'视频 {i+1}', 'url': f'https://example.org/{i}'} for i in range(30)]},
            'https://example.org/list')
        w.download_page.show_video(collection)
        wait(300)
        assert bar_for(find(w, 'collectionItems')).isVisible()
        snap(theme+'-collection-scrollbar')
        w.dialogs.info('长文本 · UI 验证', '\n'.join(['长文本滚动检查。使用统一的圆角滑块与固定点击区域。']*70))
        wait(260)
        dialog = find(w, 'dialog-info')
        assert bar_for(dialog.property('contentItem')).isVisible()
        snap(theme+'-long-dialog-scrollbar')
        w.dialogs.sessions[-1].reject()
        wait(200)
        cases.append([theme, 'scrollbars', 'download / collection / profile / dialog'])
        w.download_page.show_video(media)

        w._select_page(2)
        for locale in ('ru-RU', 'es-ES', 'pt-BR'):
            w.settings_page.setSetting('language', locale)
            for width in (1200, 600):
                w.root.resize(width, 900)
                for category in range(6):
                    w.settings_page.selectCategory(category)
                    wait(240)
                    w.grab()
                    for item in descendants(find(w, 'settingsPage')):
                        if item.isVisible() and item.objectName() in ('settingRowLabel', 'settingRowDescription'):
                            assert item.property('contentHeight') <= item.height()+1, (locale, width, category, item.property('text'))
                    nav = find(w, 'settingsNavigation')
                    for n in range(6):
                        item = find(w, f'settingsNav-{n}')
                        assert item.width() <= nav.width()
                    cases.append([theme, locale, width, category, 'wrapped layout'])
                snap(theme+'-settings-'+locale+'-'+str(width))
        w.settings_page.setSetting('language', 'zh-CN')
        w.root.resize(1200, 800)

    assert not w.qml_warnings, w.qml_warnings
    report = {'dpr': w.root.devicePixelRatio(), 'cases': cases, 'screenshots': pictures,
              'recordings': clips, 'qml_warnings': w.qml_warnings}
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    w.update(allowClose=True)
    w.close()
    w.dispose()
    print('UI FINAL PASS', args.expected_dpr, 'QML WARNINGS = 0')


if __name__ == '__main__':
    main()

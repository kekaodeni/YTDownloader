"""Offline acceptance for time masks, toolbar actions and download viewport."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPointF, QMetaObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, DownloadRequest, DownloadProgress, TaskStatus
from yt_downloader.ui.quick_window import MainWindow
try:
    from verify_i18n_features_ui import wait, find, reveal, assert_controls_inside
    from verify_quick_ui import sample_video
except ModuleNotFoundError:
    from scripts.verify_i18n_features_ui import wait, find, reveal, assert_controls_inside
    from scripts.verify_quick_ui import sample_video


def relative_y(window, item):
    return item.mapToItem(find(window, 'taskList'), QPointF(0, 0)).y()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-dpr', required=True, type=float)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(download_directory=str(args.output), auto_check_updates=False),
                        ytdlp_version='offline fixture', ffmpeg_description='offline fixture')
    window.root.resize(1200, 950)
    window.show()
    window.root.raise_()
    window.root.requestActivate()
    wait()
    dpr = window.root.devicePixelRatio()
    assert abs(dpr - args.expected_dpr) < .02, (dpr, args.expected_dpr)
    page = window.download_page
    captures, checks = [], []

    def capture(name):
        path = args.output / (name + '.png')
        assert window.grab().save(str(path))
        captures.append(str(path))

    for theme in ('light', 'dark'):
        window.theme.set_mode(theme)
        window.i18n.setLanguage('zh-CN')
        media = replace(sample_video(), duration=577, extractor_key='Youtube')
        page.setAdvancedToggle('advancedExpanded', False)
        page.setAdvancedToggle('clipEnabled', False)
        page.show_video(media)
        window.scroll_download_to_top()
        wait()
        assert abs(relative_y(window, find(window, 'videoPanel'))) < 2
        capture('result-top-' + theme)
        reveal(window, 'advancedOptionsToggle')
        header = find(window, 'advancedOptionsToggle')
        before = relative_y(window, header)
        point = header.mapToScene(QPointF(header.width() / 2, header.height() / 2)).toPoint()
        QTest.mouseClick(window.root, Qt.LeftButton, Qt.NoModifier, point)
        wait()
        assert page.state['advancedExpanded']
        assert abs(relative_y(window, header) - before) < 2
        checks.append(theme + ': advanced anchor')
        reveal(window, 'clipEnabled')
        toggle = find(window, 'clipEnabled')
        before = relative_y(window, toggle)
        page.setAdvancedToggle('clipEnabled', True)
        wait()
        assert abs(relative_y(window, toggle) - before) < 2
        checks.append(theme + ': clip anchor')
        first, last = find(window, 'clipStart'), find(window, 'clipEnd')
        assert first.property('inputMask') == '99:99;_'
        assert last.property('text') == '09:37'
        reveal(window, 'clipStart')
        first.forceActiveFocus()
        QMetaObject.invokeMethod(first, 'selectAll')
        for character in '0315':
            QTest.keyClick(window.root, Qt.Key(ord(character)))
        assert page.state['clipStart'] == '03:15'
        wait()
        reveal(window, 'advancedOptionsToggle')
        assert_controls_inside(window, ('clipEnabled', 'clipStart', 'clipEnd'))
        capture('clip-short-' + theme)
        page.show_video(replace(media, video_id='long', duration=4815))
        wait()
        assert first.property('inputMask') == '99:99:99;_'
        assert last.property('text') == '01:20:15'
        reveal(window, 'clipStart')
        QMetaObject.invokeMethod(first, 'selectAll')
        first.forceActiveFocus()
        for character in '010530':
            QTest.keyClick(window.root, Qt.Key(ord(character)))
        assert page.state['clipStart'] == '01:05:30'
        wait()
        reveal(window, 'advancedOptionsToggle')
        assert_controls_inside(window, ('clipEnabled', 'clipStart', 'clipEnd'))
        capture('clip-long-' + theme)
        page.show_video(replace(media, video_id='unknown', duration=None))
        wait()
        assert first.property('inputMask') == '99:99:99;_'
        assert last.property('displayText') == '__:__:__'
        assert not page.state['clipValid']
        reveal(window, 'advancedOptionsToggle')
        capture('clip-unknown-' + theme)
        page.setAdvancedToggle('clipEnabled', False)
        request = DownloadRequest('acceptance-' + theme, media, media.formats[0], args.output,
                                  'acceptance')
        page.add_task(request)
        page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 42))
        wait()
        reveal(window, 'task-' + request.task_id)
        pause = find(window, 'taskPause-' + request.task_id)
        assert pause.property('text') == '暂停'
        assert find(window, 'taskCancel-' + request.task_id).property('text') == '取消'
        capture('task-downloading-' + theme)
        page.paused_task(request.task_id)
        wait()
        assert pause.property('text') == '继续'
        capture('task-paused-' + theme)
        checks.append(theme + ': action labels, short/long/unknown time mask')
    report = dict(device_pixel_ratio=dpr, checks=checks, screenshots=captures,
                  qml_warnings=list(window.qml_warnings))
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    window.update(allowClose=True)
    window.close()
    window.dispose()
    app.processEvents()
    assert not report['qml_warnings'], report['qml_warnings']
    print(json.dumps(dict(device_pixel_ratio=dpr, checks=checks, qml_warnings=report['qml_warnings']), ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Record real Qt frames and measure a burst of 20 outward language wheel events.

Isolated settings; frame timestamps are retained for variable frame rate encoding.
PNG compression runs outside the GUI thread. No synthetic/interpolated frames.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yt_downloader.core.models import AppSettings
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.ui.quick_window import MainWindow
from scripts.verify_i18n_features_ui import find, wait


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-dpr', type=float, required=True)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(download_directory=str(args.output), auto_check_updates=False),
                        ytdlp_version='offline UI verification', ffmpeg_description='')
    window.settings_page.save_requested.connect(window.settings_page.mark_saved)
    window.root.resize(1200, 800)
    window.show()
    window.root.raise_()
    window.root.requestActivate()
    window._select_page(2)
    window.settings_page.setSetting('language', 'ja-JP')
    wait(350)
    assert abs(window.root.devicePixelRatio()-args.expected_dpr) < .02
    cases = []
    for theme in ('light', 'dark'):
        window.theme.set_mode(theme)
        combo = find(window, 'languageCombo')
        point = combo.mapToScene(QPointF(combo.width()/2, combo.height()/2)).toPoint()
        QTest.mouseClick(window.root, Qt.LeftButton, Qt.NoModifier, point)
        wait(200)
        view = find(window, 'options-languageCombo')
        popup = find(window, 'popup-languageCombo')
        bar = next(x for x in view.childItems() if x.inherits('QQuickScrollBar'))
        animation = next(x for x in view.children() if x.inherits('QQuickSequentialAnimation'))
        starts = []
        def running_changed():
            if animation.property('running'):
                starts.append(time.perf_counter())
        animation.runningChanged.connect(running_changed)
        local = view.mapToScene(QPointF(view.width()/2, view.height()/2))
        global_pos = QPointF(window.root.mapToGlobal(local.toPoint()))
        QTest.mouseMove(window.root, local.toPoint())
        top = view.property('originY')
        bottom = top + max(0, view.property('contentHeight')-view.height())
        def geometry():
            return [popup.property(x) for x in ('x','y','width','height')] + [
                bar.x(), bar.y(), bar.width(), bar.height(), bar.property('size'), bar.property('position')]
        for edge, direction, boundary in (('top', 1, top), ('bottom', -1, bottom)):
            view.setProperty('contentY', boundary)
            wait(250)
            baseline, names, index = geometry(), combo.property('model'), combo.property('currentIndex')
            folder = args.output/(theme+'-'+edge)
            folder.mkdir(exist_ok=True)
            frames, samples, events, futures = [], [], [], []
            starts.clear()
            started = time.perf_counter()
            def measure():
                samples.append(dict(at=time.perf_counter()-started,
                    offset=view.property('contentItem').mapToItem(view, QPointF()).y()+view.property('contentY'),
                    contentY=view.property('contentY'), geometry=geometry()))
            def capture():
                picture = window.grab()
                frames.append(dict(at=time.perf_counter()-started))
                futures.append(writer.submit(picture.save, str(folder/f'frame-{len(frames)-1:04d}.png')))
            def send():
                event = QWheelEvent(local, global_pos, QPoint(), QPoint(0, direction*120),
                                    Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
                QCoreApplication.sendEvent(window.root, event)
                events.append(time.perf_counter()-started)
            sample_timer = QTimer()
            sample_timer.timeout.connect(measure)
            sample_timer.start(4)
            frame_timer = QTimer()
            writer = ThreadPoolExecutor(max_workers=2) if args.record else None
            if args.record:
                capture()
                frame_timer.timeout.connect(capture)
                frame_timer.start(16)
            try:
                wait(600)
                for n in range(20):
                    QTimer.singleShot(n*3, send)
                wait(900)
            finally:
                sample_timer.stop()
                frame_timer.stop()
                if writer:
                    writer.shutdown(wait=True)
            assert len(events) == 20 and events[-1]-events[0] < .14
            assert len(starts) == 1, starts
            assert all(abs(x['offset']) <= 4.01 for x in samples)
            assert max(abs(x['offset']) for x in samples) > 3.5
            assert all(top-.01 <= x['contentY'] <= bottom+.01 for x in samples)
            assert all(x['geometry'] == baseline for x in samples)
            assert combo.property('model') == names and combo.property('currentIndex') == index
            assert abs(samples[-1]['offset']) < .01
            assert all(f.result() for f in futures)
            evidence = dict(theme=theme, edge=edge, wheel_events=events, feedback_starts=len(starts),
                            samples=samples, frames=frames, dpr=window.root.devicePixelRatio())
            (folder/'trace.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            clip = None
            if args.record:
                manifest = ['ffconcat version 1.0']
                for n, frame in enumerate(frames):
                    duration = frames[n+1]['at']-frame['at'] if n+1 < len(frames) else 1/60
                    manifest += [f"file 'frame-{n:04d}.png'", 'option framerate 60', f'duration {duration:.6f}']
                concat = folder/'frames.ffconcat'
                concat.write_text('\n'.join(manifest), encoding='utf-8')
                clip = args.output/(theme+'-'+edge+'.mp4')
                subprocess.run([str(FfmpegService().ffmpeg_path), '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'concat', '-safe', '0', '-i', str(concat), '-vf', 'scale=1200:800',
                    '-fps_mode', 'vfr', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                    '-pix_fmt', 'yuv420p', str(clip)], check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            cases.append(dict(theme=theme, edge=edge, events=20, feedback_starts=1,
                              max_offset=max(abs(x['offset']) for x in samples), clip=str(clip) if clip else None))
        animation.runningChanged.disconnect(running_changed)
        QTest.keyClick(window.root, Qt.Key_Escape)
        wait(200)
    assert not window.qml_warnings, window.qml_warnings
    (args.output/'results.json').write_text(json.dumps(dict(cases=cases, qml_warnings=window.qml_warnings,
        dpr=window.root.devicePixelRatio()), indent=2), encoding='utf-8')
    window.update(allowClose=True)
    window.close()
    window.dispose()
    print(f'PASS: DPR={args.expected_dpr}; 4 edge bursts; starts=1 per 20 events; warnings=0')


if __name__ == '__main__':
    main()

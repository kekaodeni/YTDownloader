"""Real Qt frame sequences for navigation, disclosure and the last-task boundary.

Uses offline media metadata to isolate geometry. No downloads or user data writes.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yt_downloader.core.models import AppSettings, DownloadRequest
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.ui.quick_window import MainWindow
from scripts.verify_i18n_features_ui import find, wait, reveal
from scripts.verify_quick_ui import sample_video


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-dpr', type=float, required=True)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow(AppSettings(download_directory=str(args.output), auto_check_updates=False),
                   ytdlp_version='test', ffmpeg_description='')
    w.settings_page.save_requested.connect(w.settings_page.mark_saved)
    w.download_page.remove_requested.connect(w.download_page.remove_task)
    w.root.resize(1200, 800)
    w.show()
    w.root.raise_()
    w.root.requestActivate()
    wait(400)
    assert abs(w.root.devicePixelRatio() - args.expected_dpr) < .02
    clips = []
    metrics = []
    media = sample_video()

    def click(item, local_point=None):
        point = item.mapToScene(local_point or QPointF(item.width() / 2, item.height() / 2)).toPoint()
        assert item.isVisible() and item.isEnabled()
        QTest.mouseMove(w.root, point)
        QTest.mousePress(w.root, Qt.LeftButton, Qt.NoModifier, point)
        # Render the actual pressed state before release, as in a human click.
        wait(20)
        QTest.mouseRelease(w.root, Qt.LeftButton, Qt.NoModifier, point)

    def record(name, actions, *, geometry=False, reduced=False):
        folder = args.output / name
        folder.mkdir(exist_ok=True)
        frames = []
        # PNG compression must not block the GUI animation driver.
        writer = ThreadPoolExecutor(max_workers=2) if args.record else None
        saved_frames = []
        started = time.perf_counter()
        view = find(w, 'taskList')
        def capture():
            picture = w.grab()
            assert not picture.isNull()
            data = dict(at=time.perf_counter() - started, contentHeight=view.property('contentHeight'),
                        contentY=view.property('contentY'), originY=view.property('originY'),
                        maximumContentY=max(0, view.property('contentHeight') - view.height()))
            if geometry:
                data['headerY'] = find(w, 'advancedOptionsToggle').mapToScene(QPointF()).y()
                data['clipY'] = find(w, 'clipEnabled').mapToScene(QPointF()).y()
                data['clipVisible'] = find(w, 'clipEnabled').isVisible()
                data['reserve'] = find(w, 'viewportAnchor').property('boundaryReserve')
            if name.endswith('settings'):
                hosts = [find(w, f'settingsHost-{i}') for i in range(6)]
                data['alphas'] = [h.opacity() for h in hosts]
                assert max(data['alphas']) >= .45, data
                if reduced:
                    assert all(h.property('visualOffset') == 0 for h in hosts)
            if args.record:
                saved_frames.append(writer.submit(picture.save, str(folder / f'frame-{len(frames):04d}.png')))
            frames.append(data)
        capture()
        timer = QTimer()
        timer.timeout.connect(capture)
        timer.start(16)
        try:
            for action in actions:
                action()
                wait(500)
        except Exception:
            w.grab().save(str(folder / 'failure.png'))
            (folder / 'failure-frames.json').write_text(json.dumps(frames, indent=2), encoding='utf-8')
            raise
        finally:
            timer.stop()
        capture()
        if writer is not None:
            writer.shutdown(wait=True)
            assert all(result.result() for result in saved_frames)
        if geometry:
            assert find(w, 'viewportAnchor').property('boundaryReserve') == 0
            assert not find(w, 'viewportAnchor').property('mutating')
            # Boundary following may move the control continuously. Measure
            # steps and timestamps, not just the different endpoints.
            for key in ('headerY', 'clipY'):
                pairs = [(a, b) for a, b in zip(frames, frames[1:])
                         if key != 'clipY' or (a['clipVisible'] and b['clipVisible'])]
                if not pairs:
                    continue
                metrics.append(dict(case=name, control=key,
                                    max_frame_step=max(abs(b[key] - a[key]) for a, b in pairs)))
        (folder / 'frames.json').write_text(json.dumps(frames, indent=2), encoding='utf-8')
        if args.record:
            ffmpeg = FfmpegService().ffmpeg_path
            # Preserve actual capture timestamps; PNG writing can skip frames.
            manifest = ['ffconcat version 1.0']
            for i, frame in enumerate(frames):
                duration = frames[i+1]['at']-frame['at'] if i+1 < len(frames) else 1/60
                manifest.extend([f"file 'frame-{i:04d}.png'", 'option framerate 60', f'duration {duration:.6f}'])
            concat = folder / 'frames.ffconcat'
            concat.write_text('\n'.join(manifest), encoding='utf-8')
            subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0',
                            '-i', str(concat), '-vf', 'scale=1200:800', '-fps_mode', 'vfr',
                            '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-pix_fmt', 'yuv420p',
                            str(args.output / (name + '.mp4'))], check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        clips.append(name)

    for theme in ('light', 'dark'):
        w.theme.set_mode(theme)
        w.settings_page.setSetting('reduce_motion', False)
        w._select_page(0)
        wait(300)
        record(theme + '-main', [lambda n=n: click(find(w, f'nav-{n}')) for n in (1, 2, 3, 0)])
        w._select_page(2)
        wait(300)
        record(theme + '-settings', [lambda n=n: click(find(w, f'settingsNav-{n}')) for n in range(1, 6)])
        w._select_page(0)
        page = w.download_page
        page.show_video(media)
        page.add_task(DownloadRequest('motion', media, media.formats[0], args.output, 'motion'))
        page.setAdvancedToggle('advancedExpanded', False)
        wait(350)
        reveal(w, 'advancedOptionsToggle', 140)
        wait(80)
        def advanced():
            before = page.state['advancedExpanded']
            control = find(w, 'advancedOptionsToggle')
            click(control)
            assert page.state['advancedExpanded'] != before, dict(
                before=before, enabled=control.isEnabled(), visible=control.isVisible(),
                screenY=control.mapToScene(QPointF()).y(), width=control.width(), height=control.height(),
                rootActive=w.root.isActive(), qmlWarnings=w.qml_warnings)
        record(theme + '-task-advanced', [advanced, advanced], geometry=True)
        advanced()
        wait(300)
        reveal(w, 'clipEnabled', 140)
        wait(80)
        def clip():
            before = page.state['clipEnabled']
            item = find(w, 'clipEnabled')
            click(item, QPointF(item.width() - 31, item.height() / 2))
            assert page.state['clipEnabled'] != before
        record(theme + '-task-clip', [clip, clip], geometry=True)
        # Keep the disclosure in view while the task is removed from its model.
        record(theme + '-delete-last', [lambda: page.remove_task('motion')], geometry=True)
        assert page.tasks.count == 0
        reveal(w, 'advancedOptionsToggle', 140)
        wait(80)
        record(theme + '-empty-advanced', [advanced, advanced], geometry=True)
        if not page.state['advancedExpanded']:
            advanced()
            wait(300)
        reveal(w, 'clipEnabled', 140)
        wait(80)
        record(theme + '-empty-clip', [clip, clip], geometry=True)
        w._select_page(2)
        w.settings_page.setSetting('reduce_motion', True)
        w.settings_page.selectCategory(0)
        wait(300)
        record(theme + '-reduced-settings', [lambda n=n: click(find(w, f'settingsNav-{n}')) for n in range(1, 6)], reduced=True)
    assert not w.qml_warnings, w.qml_warnings
    report = dict(dpr=w.root.devicePixelRatio(), clips=clips, metrics=metrics, qml_warnings=w.qml_warnings,
                  motion_source='MotionTokens.qml', frame_sequence_is_real_qt=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.record:
        videos = ''.join(f'<h2>{name}</h2><video controls loop width="960" src="{name}.mp4"></video>' for name in clips)
        (args.output / 'gallery.html').write_text('<!doctype html><meta charset="utf-8"><title>Qt Motion</title>'
                                               '<style>body{background:#181c24;color:white;font:16px Segoe UI;margin:32px}video{max-width:100%}</style>'
                                               '<h1>Actual Qt Quick frames</h1><p>Light / Dark; offline geometry fixture, no runtime downloads.</p>' + videos,
                                               encoding='utf-8')
    w.update(allowClose=True)
    w.close()
    w.dispose()
    print('MOTION PASS', args.expected_dpr, len(clips), 'QML warnings=0')


if __name__ == '__main__':
    main()

"""Offline source UI acceptance; run separately at each QT_SCALE_FACTOR."""
import argparse
import json
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlExpression
from PySide6.QtWidgets import QApplication
from semver import Version

from yt_downloader import __version__
from yt_downloader.core.models import AppSettings
from yt_downloader.ui.quick_dialogs import UpdateSession
from yt_downloader.ui.quick_window import MainWindow
from yt_downloader.updates.models import UpdateCapability, UpdateManifest, UpdatePackage, UpdateProgress, UpdateState


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-dpr', type=float, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(auto_check_updates=False), ytdlp_version='offline acceptance', ffmpeg_description='offline acceptance')
    window.show()
    window.root.raise_()
    window.root.requestActivate()
    window.root.resize(900, 650)
    if abs(window.root.devicePixelRatio() - args.expected_dpr) > .01:
        window.dispose()
        raise ValueError('Actual Qt device pixel ratio differs from the requested acceptance scale')
    manifest = UpdateManifest(
        Version.parse('0.5.1'), '2026-09-17T00:00:00Z', Version.parse('0.4.2'), 2,
        'offline-fixture', ('界面离线验收说明：下载完成后由用户确认重启。\n' * 24) + '<b>保持纯文本</b>',
        'Offline acceptance notes. Confirm restart after verification.\n' * 24,
        'https://example.invalid/notes', UpdatePackage('offline.zip', 'https://example.invalid/offline.zip', 100_000_000, 200_000_000, '0'*64),
    )
    captures = []

    def find(name):
        obj = window.root.findChild(QObject, name)
        assert obj is not None, name
        return obj

    def snapshot(name):
        path = args.output / (name + '.png')
        assert window.grab().save(str(path))
        captures.append(path.name)

    def steps():
        yield 400
        for mode in ('light', 'dark'):
            window.theme.set_mode(mode)
            for page, name in ((3, 'about'), (2, 'settings')):
                window._select_page(page)
                yield 400
                if page == 2:
                    scroll = find('settingsScroll')
                    switch = find('autoCheckUpdates')
                    offset = switch.mapToItem(scroll, QPointF(0, 0)).y()
                    scroll.setProperty('contentY', min(scroll.property('contentHeight') - scroll.height(),
                                                       max(0, scroll.property('contentY') + offset - scroll.height()/2)))
                    yield 200
                snapshot(f'{mode}-{name}')
            window._select_page(3)
            yield 300
            session = UpdateSession(manifest, UpdateCapability.AUTO_INSTALL, window)
            session.show()
            yield 350
            notes = find('updateNotes')
            assert '<b>' in notes.property('text')
            plain = QQmlExpression(window.engine.rootContext(), notes, 'textFormat === 0')
            assert plain.evaluate()[0] is True  # TextEdit.PlainText
            scroll = find('updateNotesScroll').property('contentItem')
            assert scroll.property('contentHeight') > scroll.property('height')
            scroll.setProperty('contentY', 60)
            yield 150
            assert scroll.property('contentY') > 0
            snapshot(f'{mode}-available')
            language = find('updateLanguage')
            language.forceActiveFocus()
            QTest.keyClick(window.root, Qt.Key.Key_Down)
            yield 150
            assert session.state['language'] == 'en'
            session.set_state(UpdateState.DOWNLOADING)
            session.set_progress(UpdateProgress(25_000_000, 100_000_000, 5_000_000, 15))
            yield 200
            snapshot(f'{mode}-downloading')
            session.set_state(UpdateState.READY_TO_INSTALL)
            yield 200
            button = find('updateInstall')
            assert button.property('visible') and button.property('enabled')
            QTest.mouseMove(window.root, button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint())
            yield 200
            assert button.property('hovered')
            snapshot(f'{mode}-ready-hover')
            QTest.keyClick(window.root, Qt.Key.Key_Escape)
            yield 250
            assert not window.dialogs.sessions
            window.set_reduce_motion(True)
            reduced = UpdateSession(manifest, UpdateCapability.AUTO_INSTALL, window)
            reduced.show()
            reduced.set_state(UpdateState.PREPARING_INSTALL)
            yield 200
            QTest.keyClick(window.root, Qt.Key.Key_Escape)
            assert reduced.state['open']
            snapshot(f'{mode}-preparing-reduced-motion')
            reduced.set_state(UpdateState.FAILED, operation='prepare')
            yield 150
            assert reduced.state['closeEnabled'] and reduced.state['canInstall']
            reduced.reject()
            window.set_reduce_motion(False)
            yield 250
        assert not window.qml_warnings, window.qml_warnings
        report = dict(app_version=__version__, source_module=__import__('yt_downloader').__file__,
                      dpr=window.root.devicePixelRatio(), screenshots=captures, qml_warnings=[],
                      checks=['about', 'settings', 'long_plain_notes', 'scroll', 'keyboard_language', 'escape', 'hover', 'reduce_motion', 'prepare_failure'])
        (args.output/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
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
        window.dispose()


if __name__ == '__main__':
    raise SystemExit(main())

import pytest
from PySide6.QtCore import QObject, QTimer, QPointF, QEvent
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from yt_downloader.core.models import AppSettings
from yt_downloader.ui.quick_window import MainWindow

def run_frames(app, milliseconds=280):
    """Qt Quick's animation driver requires QApplication's main event loop."""
    QTimer.singleShot(milliseconds, app.quit)
    app.exec()

def find_item(window, name):
    item = window.root.findChild(QObject, name)
    if item is None:
        pending = [window.root.contentItem()]
        while pending:
            candidate = pending.pop()
            if candidate.objectName() == name:
                return candidate
            pending.extend(candidate.childItems())
    assert item is not None, name
    return item

def click_item(window, item, button=Qt.MouseButton.LeftButton):
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(window.root, button, Qt.KeyboardModifier.NoModifier, point)

@pytest.fixture
def quick_window(qapp, tmp_path):
    qapp.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(download_directory=str(tmp_path), auto_check_updates=False),
                        ytdlp_version='test', ffmpeg_description='test')
    window.show()
    run_frames(qapp, 120)
    yield window
    for session in tuple(window.dialogs.sessions):
        session.reject()
    run_frames(qapp, 240)
    warnings = list(window.qml_warnings)
    window.update(allowClose=True)
    window.close()
    window.dispose()
    window.theme.deleteLater()
    window.deleteLater()
    # processEvents alone leaves DeferredDelete queued when no main loop is active.
    # Finish destruction on the GUI thread before subsequent worker tests run.
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    import gc
    import shiboken6
    assert not shiboken6.isValid(window)
    gc.collect()
    assert not warnings

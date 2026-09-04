from PySide6.QtWidgets import QStackedWidget, QWidget

from yt_downloader.ui.motion import MotionManager
from yt_downloader.ui.snapshot import window_budget


def test_rapid_page_switch_retargets_current_composite_without_queue(qapp, qtbot):
    stack = QStackedWidget()
    pages = [QWidget() for _ in range(3)]
    for page in pages:
        stack.addWidget(page)
    qtbot.addWidget(stack)
    stack.resize(600, 400)
    stack.show()
    qapp.processEvents()
    manager = MotionManager()
    manager.switch_page(stack, 1)
    qtbot.wait(60)
    first_overlay = manager._snapshots[id(stack)]
    manager.switch_page(stack, 2)
    assert stack.currentIndex() == 2
    assert first_overlay.finished_once
    assert len(manager._snapshots) == 1
    assert manager.active_count == 1
    assert all(page.graphicsEffect() is None for page in pages)
    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1000)
    assert window_budget(stack).used == 0

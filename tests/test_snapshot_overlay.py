from PySide6.QtCore import QRect
from PySide6.QtGui import QPixmap

from yt_downloader.ui.snapshot import SnapshotBudget, backing_bytes


def test_budget_charges_physical_pixels_including_dpr_squared(qapp):
    pixmap = QPixmap(400, 200)
    pixmap.setDevicePixelRatio(2)
    assert pixmap.deviceIndependentSize().width() == 200
    assert backing_bytes(pixmap) == 400 * 200 * 4
    budget = SnapshotBudget(limit=400 * 200 * 4)
    assert budget.reserve(backing_bytes(pixmap))
    assert not budget.reserve(1)
    assert budget.used == budget.limit
    budget.release(backing_bytes(pixmap))
    assert budget.used == 0


def test_capture_is_clipped_to_visible_ancestor_and_releases_lease(qapp, qtbot):
    from PySide6.QtWidgets import QWidget
    from yt_downloader.ui.snapshot import capture_visible, window_budget

    viewport = QWidget()
    viewport.resize(240, 160)
    content = QWidget(viewport)
    content.setGeometry(0, -80, 240, 10000)
    qtbot.addWidget(viewport)
    viewport.show()
    qapp.processEvents()
    frame = capture_visible(content)
    assert frame is not None
    assert frame.rect == QRect(0, 80, 240, 160)
    assert frame.pixmap.deviceIndependentSize().height() == 160
    assert window_budget(viewport) is window_budget(content)
    assert window_budget(content).used == backing_bytes(frame.pixmap)
    frame.release()
    frame.release()
    assert window_budget(content).used == 0
    denied = SnapshotBudget(limit=1)
    assert capture_visible(content, budget=denied) is None
    assert denied.used == 0


def test_overlay_finishes_before_click_and_preserves_one_native_action(qapp, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget, QPushButton
    from yt_downloader.ui.motion import PresentationState
    from yt_downloader.ui.snapshot import SnapshotOverlay, capture_visible, window_budget

    host = QWidget()
    host.resize(240, 160)
    button = QPushButton('确定', host)
    qtbot.addWidget(host)
    host.show()
    frame = capture_visible(host)
    overlay = SnapshotOverlay(host, frame)
    overlay.play(PresentationState(opacity=0, y=-5), duration=190)
    actions = []
    button.clicked.connect(lambda: actions.append(window_budget(host).used))
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert actions == [0]
    assert overlay.finished_once
    assert not overlay.isVisible()


def test_overlay_settles_on_host_resize_and_releases_capture(qapp, qtbot):
    from PySide6.QtWidgets import QWidget
    from yt_downloader.ui.snapshot import SnapshotOverlay, capture_visible, window_budget

    host = QWidget()
    qtbot.addWidget(host)
    host.show()
    overlay = SnapshotOverlay(host, capture_visible(host))
    overlay.show()
    host.resize(host.width() + 1, host.height())
    assert overlay.finished_once
    assert window_budget(host).used == 0


def test_layout_change_is_once_and_skips_animation_when_window_budget_is_full(qapp, qtbot):
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
    from yt_downloader.ui.motion import MotionManager
    from yt_downloader.ui.snapshot import window_budget

    host = QWidget()
    layout = QVBoxLayout(host)
    first, second = QLabel('first'), QLabel('second')
    layout.addWidget(first)
    layout.addWidget(second)
    qtbot.addWidget(host)
    host.show()
    qapp.processEvents()
    window_budget(host).limit = 1
    changes = []
    manager = MotionManager()
    manager.retire(first, lambda: changes.append(True))
    assert changes == [True]
    assert not first.isVisible()
    assert second.isVisible()
    assert manager.active_count == 0
    assert window_budget(host).used == 0

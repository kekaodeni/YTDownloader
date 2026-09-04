from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from yt_downloader.ui.motion import MotionManager
from yt_downloader.ui.smooth_scroll import SmoothScrollController


def wheel(pixel_y=0, angle_y=0):
    return QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, pixel_y), QPoint(0, angle_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_discrete_wheel_retargets_and_pixel_delta_stays_native(qapp, qtbot):
    area = QScrollArea()
    content = QWidget()
    content.resize(200, 3000)
    area.setWidget(content)
    area.resize(240, 300)
    qtbot.addWidget(area)
    area.show()
    area.verticalScrollBar().setValue(500)
    motion = MotionManager()
    smooth = SmoothScrollController(motion)
    smooth.install(area)
    QApplication.sendEvent(area.viewport(), wheel(angle_y=-120))
    assert smooth.active_count == 1
    first_target = smooth.target(area)
    assert first_target > 500
    QApplication.sendEvent(area.viewport(), wheel(angle_y=120))
    assert smooth.active_count == 1
    assert smooth.target(area) < first_target
    smooth.stop(area)
    QApplication.sendEvent(area.viewport(), wheel(pixel_y=12))
    assert smooth.active_count == 0


def test_reduced_motion_stops_discrete_wheel_without_delayed_scroll(qapp, qtbot):
    area = QScrollArea()
    content = QWidget(); content.resize(200, 3000); area.setWidget(content)
    qtbot.addWidget(area); area.show()
    motion = MotionManager()
    smooth = SmoothScrollController(motion); smooth.install(area)
    QApplication.sendEvent(area.viewport(), wheel(angle_y=-120))
    assert smooth.active_count == 1
    motion.set_reduce_motion(True)
    assert smooth.active_count == 0

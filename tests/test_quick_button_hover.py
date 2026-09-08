import pytest
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtTest import QTest
from conftest import find_item, run_frames
from yt_downloader.core.errors import AppError
from yt_downloader.ui.quick_dialogs import ErrorSession


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_button_hover_pixels_never_flash_past_either_endpoint(quick_window, qapp, mode):
    window = quick_window
    window.theme.set_mode(mode)
    error = ErrorSession(AppError("test", "封面处理失败", "test detail"), "report", window)
    error.show()
    run_frames(qapp, 250)
    button = find_item(window, "errorDetails")
    for appearance in ("quiet", "normal", "primary", "danger", "nav"):
        button.setProperty("appearance", appearance)
        QTest.mouseMove(window.root, QPointF(10, 10).toPoint())
        run_frames(qapp, 160)
        point = button.mapToScene(QPointF(8, 8))
        def pixel():
            frame = window.grab()
            dpr = frame.devicePixelRatio()
            color = frame.pixelColor(round(point.x()*dpr), round(point.y()*dpr))
            return (color.red(), color.green(), color.blue())
        start = pixel()
        frames = []
        QTest.mouseMove(window.root, button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint())
        for delay in range(10, 161, 10):
            QTimer.singleShot(delay, lambda: frames.append(pixel()))
        run_frames(qapp, 200)
        end = pixel()
        for sample in frames:
            for channel, a, b in zip(sample, start, end):
                assert min(a, b)-3 <= channel <= max(a, b)+3, (mode, appearance, start, end, sample)
    error.reject()

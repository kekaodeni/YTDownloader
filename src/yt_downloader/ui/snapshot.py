"""Bounded, disposable presentation snapshots; never owns business widgets."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
import weakref

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

from yt_downloader.ui.motion import AnimationController, PresentationState


def backing_bytes(pixmap: QPixmap) -> int:
    """QPixmap width/height are physical pixels, not device-independent size."""
    return ((pixmap.width() * pixmap.depth() + 31) // 32 * 4) * pixmap.height()


@dataclass(slots=True)
class SnapshotBudget:
    limit: int = 64 * 1024 * 1024
    used: int = 0

    def reserve(self, size: int) -> bool:
        if size < 0 or self.used + size > self.limit:
            return False
        self.used += size
        return True

    def release(self, size: int) -> None:
        if not 0 <= size <= self.used:
            raise ValueError("Invalid snapshot lease release")
        self.used -= size


@dataclass(slots=True)
class SnapshotFrame:
    pixmap: QPixmap
    rect: QRect
    budget: SnapshotBudget
    charged: int

    def release(self) -> None:
        self.pixmap = QPixmap()
        if self.charged:
            self.budget.release(self.charged)
            self.charged = 0


def window_budget(widget: QWidget) -> SnapshotBudget:
    window = widget.window()
    if not hasattr(window, '_snapshot_budget'):
        window._snapshot_budget = SnapshotBudget()
    return window._snapshot_budget


def capture_visible(widget: QWidget, *, budget: SnapshotBudget | None = None) -> SnapshotFrame | None:
    if not widget.isVisible():
        return None
    rect = widget.visibleRegion().boundingRect().intersected(widget.rect())
    if rect.isEmpty():
        return None
    budget = budget if budget is not None else window_budget(widget)
    dpr = widget.devicePixelRatioF()
    width, height = ceil(rect.width() * dpr), ceil(rect.height() * dpr)
    reserved = ((width * max(32, QPixmap.defaultDepth()) + 31) // 32 * 4) * height
    if not budget.reserve(reserved):
        return None
    try:
        pixmap = widget.grab(rect)
        size = backing_bytes(pixmap)
        if size > reserved:
            if not budget.reserve(size - reserved):
                budget.release(reserved)
                return None
        else:
            budget.release(reserved - size)
    except Exception:
        budget.release(reserved)
        raise
    return SnapshotFrame(pixmap, rect, budget, size)


class SnapshotOverlay(QWidget):
    """Input-transparent proxy, invalidated before native input is dispatched."""

    finished = Signal()
    _INPUT = {QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel,
              QEvent.Type.TouchBegin, QEvent.Type.ContextMenu}
    _INVALIDATE = {QEvent.Type.Resize, QEvent.Type.Hide, QEvent.Type.Close,
                   QEvent.Type.DevicePixelRatioChange, QEvent.Type.PaletteChange,
                   QEvent.Type.StyleChange}

    def __init__(self, host: QWidget, frame: SnapshotFrame, *, geometry: QRect | None = None):
        super().__init__(host)
        self._host = weakref.ref(host)
        self.frame = frame
        self.finished_once = False
        self.setObjectName('motionSnapshotOverlay')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setGeometry(frame.rect if geometry is None else geometry)
        self.controller = AnimationController(parent=self)
        self.controller.presentation_changed.connect(self._present)
        self.controller.finished.connect(self.cleanup)
        # The lease must also be released when Qt destroys the whole host tree.
        # A plain Python lease is not a QObject receiver. Keep it alive explicitly
        # until destroyed; never hand PySide a weak bound method on a slots dataclass.
        self.destroyed.connect(lambda _object=None, lease=frame: lease.release())
        QApplication.instance().installEventFilter(self)

    def play(self, target: PresentationState, *, duration: int, easing=None) -> None:
        self.show()
        self.raise_()
        options = {} if easing is None else {'easing': easing}
        self.controller.retarget(target, duration=duration, **options)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        state = self.controller.presentation
        painter.setOpacity(state.opacity)
        center = self.rect().center()
        painter.translate(center.x() + state.x, center.y() + state.y)
        painter.scale(state.scale, state.scale)
        painter.translate(-center.x(), -center.y())
        painter.drawPixmap(QPointF(0, 0), self.frame.pixmap)

    def _present(self, _state: PresentationState) -> None:
        self.update()

    def eventFilter(self, watched, event) -> bool:
        if self.finished_once or watched is self:
            return False
        host = self._host()
        if host is None or not isValid(host):
            return False
        if isinstance(watched, QWidget):
            if event.type() in self._INPUT and (watched is host or host.isAncestorOf(watched)):
                self.cleanup()
            elif event.type() in self._INVALIDATE and (
                watched is host or watched.isAncestorOf(host)
            ):
                self.cleanup()
        return False

    def cleanup(self) -> None:
        if self.finished_once:
            return
        self.finished_once = True
        self.controller.cleanup()
        QApplication.instance().removeEventFilter(self)
        self.hide()
        self.frame.release()
        self.finished.emit()
        self.deleteLater()

"""A double-buffered thumbnail surface with interruption-safe cross-fades."""
from __future__ import annotations

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, Qt
from PySide6.QtGui import QPainter, QPixmap, QResizeEvent
from PySide6.QtWidgets import QStyle, QStyleOption, QWidget

from yt_downloader.ui.motion import AnimationController, MotionManager, MotionTokens, PresentationState


class ThumbnailCrossFadeWidget(QWidget):
    def __init__(self, parent: QWidget | None = None, *, motion: MotionManager | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._motion = motion
        self._source = QPixmap()
        self._current = QPixmap()
        self.previous_pixmap = QPixmap()
        self._text = '缩略图'
        self._progress = 1.0
        self._controller = AnimationController(parent=self)
        self._controller.presentation_changed.connect(self._present)
        self._controller.finished.connect(self._settle)
        if motion is not None:
            motion.reduced_motion_changed.connect(self._reduce_motion_changed)

    @property
    def is_animating(self) -> bool:
        return self._controller.state() == QAbstractAnimation.State.Running

    def pixmap(self) -> QPixmap:
        return self._source

    def text(self) -> str:
        return self._text

    def clear(self) -> None:
        self._controller.stop()
        self._source = QPixmap()
        self._current = QPixmap()
        self.previous_pixmap = QPixmap()
        self._text = ''
        self._progress = 1.0
        self.update()

    def setText(self, text: str) -> None:
        self.clear()
        self._text = text
        self.update()

    def setPixmap(self, pixmap: QPixmap) -> None:
        new_pixmap = self._fit(pixmap)
        self._source = pixmap
        self._text = ''
        if self._current.isNull() or not self.isVisible() or (self._motion and self._motion.reduce_motion):
            self._current = new_pixmap
            self.previous_pixmap = QPixmap()
            self._progress = 1.0
            self.update()
            return
        self.previous_pixmap = self.grab() if self.is_animating else self._current
        self._current = new_pixmap
        self._progress = 0.0
        self._controller.presentation = PresentationState(opacity=0)
        self._controller.retarget(
            PresentationState(), duration=MotionTokens.THUMBNAIL,
            easing=QEasingCurve.Type.OutQuart,
        )

    def _fit(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull() or self.size().isEmpty():
            return QPixmap()
        return pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _present(self, state: PresentationState) -> None:
        self._progress = state.opacity
        self.update()

    def _settle(self) -> None:
        self._progress = 1.0
        self.previous_pixmap = QPixmap()
        self.update()

    def _reduce_motion_changed(self, enabled: bool) -> None:
        if enabled:
            self._controller.stop()
            self._settle()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._controller.stop()
        self.previous_pixmap = QPixmap()
        self._current = self._fit(self._source)
        self._progress = 1.0
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
        if not self.previous_pixmap.isNull():
            painter.setOpacity(1 - self._progress)
            painter.drawPixmap(0, 0, self.previous_pixmap)
        if not self._current.isNull():
            painter.setOpacity(self._progress)
            painter.drawPixmap(0, 0, self._current)
        elif self._text:
            painter.setOpacity(1)
            painter.setPen(self.palette().windowText().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)

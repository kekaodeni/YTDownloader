"""Interruptible smoothing for discrete mouse wheels only."""
from __future__ import annotations

from dataclasses import dataclass
import weakref

from PySide6.QtCore import QAbstractAnimation, QEvent, QEasingCurve, QObject, QVariantAnimation
from PySide6.QtWidgets import QAbstractScrollArea
from shiboken6 import delete as delete_qobject, isValid

from yt_downloader.ui.motion import MotionManager, MotionTokens


@dataclass(slots=True)
class _ScrollState:
    area: weakref.ReferenceType[QAbstractScrollArea]
    animation: QVariantAnimation
    target: int


class SmoothScrollController(QObject):
    def __init__(self, motion: MotionManager, parent: QObject | None = None) -> None:
        super().__init__(parent or motion)
        self.motion = motion
        self._areas: dict[int, weakref.ReferenceType[QAbstractScrollArea]] = {}
        self._bars: dict[int, weakref.ReferenceType[QAbstractScrollArea]] = {}
        self._active: dict[int, _ScrollState] = {}
        motion.reduced_motion_changed.connect(self._reduce_motion_changed)

    @property
    def active_count(self) -> int:
        self._prune()
        return len(self._active)

    def install(self, area: QAbstractScrollArea) -> None:
        for watched in (area, area.viewport(), area.verticalScrollBar(), area.horizontalScrollBar()):
            watched.installEventFilter(self)
            self._areas[id(watched)] = weakref.ref(area)
        bar = area.verticalScrollBar()
        self._bars[id(bar)] = weakref.ref(area)
        bar.sliderPressed.connect(self._slider_pressed)

    def _slider_pressed(self) -> None:
        area_ref = self._bars.get(id(self.sender()))
        self.stop(area_ref() if area_ref else None)

    def target(self, area: QAbstractScrollArea) -> int | None:
        state = self._active.get(id(area))
        return state.target if state else None

    def eventFilter(self, watched, event) -> bool:
        area_ref = self._areas.get(id(watched))
        area = area_ref() if area_ref else None
        if area is None or not isValid(area):
            return False
        if event.type() is QEvent.Type.Wheel:
            if not event.pixelDelta().isNull() or event.angleDelta().y() == 0:
                self.stop(area)
                return False
            if self.motion.reduce_motion:
                return False
            steps = -event.angleDelta().y() / 120.0
            self._scroll(area, steps)
            event.accept()
            return True
        if event.type() in {QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress,
                            QEvent.Type.TouchBegin}:
            self.stop(area)
        return False

    def _scroll(self, area: QAbstractScrollArea, steps: float) -> None:
        bar = area.verticalScrollBar()
        start = bar.value()
        step = max(bar.singleStep() * 3, 48)
        target = max(bar.minimum(), min(bar.maximum(), round(start + steps * step)))
        self.stop(area)
        if target == start:
            return
        animation = QVariantAnimation(self)
        animation.setStartValue(start)
        animation.setEndValue(target)
        animation.setDuration(int(MotionTokens.SCROLL))
        animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        state = _ScrollState(weakref.ref(area), animation, target)
        self._active[id(area)] = state
        animation.valueChanged.connect(self._value_changed)
        animation.finished.connect(self._animation_finished)
        animation.start()

    def _value_changed(self, value) -> None:
        animation = self.sender()
        for state in self._active.values():
            if state.animation is animation:
                area = state.area()
                if area is not None and isValid(area):
                    area.verticalScrollBar().setValue(int(value))
                break

    def _animation_finished(self) -> None:
        animation = self.sender()
        for key, state in tuple(self._active.items()):
            if state.animation is animation:
                self.stop(state.area())
                break

    def stop(self, area: QAbstractScrollArea | None) -> None:
        if area is None:
            return
        state = self._active.pop(id(area), None)
        if state is not None and isValid(state.animation):
            state.animation.stop()
            delete_qobject(state.animation)

    def _reduce_motion_changed(self, enabled: bool) -> None:
        if enabled:
            for state in tuple(self._active.values()):
                self.stop(state.area())

    def _prune(self) -> None:
        for key, state in tuple(self._active.items()):
            area = state.area()
            if area is None or not isValid(area):
                state.animation.stop()
                self._active.pop(key, None)

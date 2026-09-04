"""Central, bounded motion for short Fluent-style state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable
import weakref

from PySide6.QtCore import (
    QAbstractAnimation,
    QAnimationGroup,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QObject,
    QTimer,
    Qt,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QStackedWidget, QWidget
from shiboken6 import delete as delete_qobject, isValid


class MotionDuration(IntEnum):
    FAST = 140
    NORMAL = 240
    EMPHASIS = 320


@dataclass(slots=True)
class _MotionState:
    widget: weakref.ReferenceType[QWidget]
    animation: QAbstractAnimation
    effect: QGraphicsOpacityEffect | None = None
    dispose_widget: bool = False
    finishing: bool = False


class MotionManager(QObject):
    def __init__(self, reduce_motion: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.reduce_motion = reduce_motion
        self._active: dict[int, _MotionState] = {}

    @property
    def active_count(self) -> int:
        return len(self._active)

    def set_reduce_motion(self, enabled: bool) -> None:
        self.reduce_motion = bool(enabled)
        if self.reduce_motion:
            for key in tuple(self._active):
                self._finish(key, stopped=True)

    def switch_page(self, stack: QStackedWidget, index: int) -> None:
        if not 0 <= index < stack.count():
            return
        changed = stack.currentIndex() != index
        stack.setCurrentIndex(index)
        if self.reduce_motion or not changed:
            return
        target = stack.widget(index)
        self._fade(target, MotionDuration.NORMAL)

    def reveal(self, widget: QWidget) -> None:
        widget.show()
        if self.reduce_motion:
            return
        self._fade(widget, MotionDuration.EMPHASIS)

    def retire(self, widget: QWidget, on_finished: Callable[[], None]) -> None:
        if self.reduce_motion or not widget.isVisible():
            widget.hide()
            on_finished()
            return
        key = id(widget)
        self._finish(key, stopped=True)
        parent = widget.parentWidget()
        if parent is None:
            widget.hide()
            on_finished()
            return
        if parent.layout():
            parent.layout().activate()
        proxy = QLabel(parent)
        proxy.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        proxy.setPixmap(widget.grab())
        proxy.setScaledContents(True)
        proxy.setGeometry(widget.geometry())
        proxy.show()
        proxy.raise_()
        effect = QGraphicsOpacityEffect(proxy)
        effect.setOpacity(1.0)
        proxy.setGraphicsEffect(effect)
        opacity = QPropertyAnimation(effect, b"opacity", self)
        opacity.setDuration(int(MotionDuration.NORMAL))
        opacity.setStartValue(1.0)
        opacity.setEndValue(0.0)
        opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        position = QPropertyAnimation(proxy, b"pos", self)
        position.setDuration(int(MotionDuration.NORMAL))
        position.setStartValue(proxy.pos())
        position.setEndValue(proxy.pos() + QPoint(0, -6))
        position.setEasingCurve(QEasingCurve.Type.OutCubic)
        group = QParallelAnimationGroup(self)
        group.addAnimation(opacity)
        group.addAnimation(position)
        widget.hide()
        on_finished()
        if parent.layout():
            parent.layout().activate()
        self._register(proxy, group, effect=effect, dispose_widget=True)

    def feedback(self, widget: QWidget) -> None:
        if self.reduce_motion or not widget.isVisible():
            return
        key = id(widget)
        self._finish(key, stopped=True)
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(int(MotionDuration.FAST))
        animation.setStartValue(1.0)
        animation.setKeyValueAt(0.35, 0.82)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._register(widget, animation, effect=effect)

    def _fade(
        self,
        widget: QWidget,
        duration: MotionDuration,
    ) -> None:
        key = id(widget)
        self._finish(key, stopped=True)
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        opacity = QPropertyAnimation(effect, b"opacity", self)
        opacity.setDuration(int(duration))
        opacity.setStartValue(0.0)
        opacity.setEndValue(1.0)
        opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._register(widget, opacity, effect=effect)

    def _register(
        self,
        widget: QWidget,
        animation: QAbstractAnimation,
        *,
        effect: QGraphicsOpacityEffect | None = None,
        dispose_widget: bool = False,
    ) -> None:
        key = id(widget)
        state = _MotionState(
            weakref.ref(widget),
            animation,
            effect,
            dispose_widget,
        )
        self._active[key] = state
        animation.finished.connect(lambda current=key, value=state: self._schedule_finish(current, value))
        animation.start()

    def _finish(self, key: int, *, stopped: bool = False) -> None:
        state = self._active.get(key)
        if state is None:
            return
        if stopped:
            self._destroy_state(key, state)
        else:
            self._schedule_finish(key, state)

    def _schedule_finish(self, key: int, state: _MotionState) -> None:
        if state.finishing:
            return
        state.finishing = True
        QTimer.singleShot(0, lambda: self._destroy_state(key, state))

    def _destroy_state(self, key: int, state: _MotionState) -> None:
        if isValid(state.animation):
            state.animation.stop()
        widget = state.widget()
        if widget is not None:
            try:
                if state.effect is not None:
                    state.effect.setOpacity(1.0)
                if state.dispose_widget:
                    widget.hide()
            except RuntimeError:
                pass
        if isValid(state.animation):
            self._detach_effect_target(state.animation, state.effect)
            delete_qobject(state.animation)
        if widget is not None:
            try:
                if state.effect is not None and widget.graphicsEffect() is state.effect:
                    widget.setGraphicsEffect(None)
            except RuntimeError:
                pass
        if self._active.get(key) is state:
            self._active.pop(key, None)
        if state.dispose_widget and widget is not None:
            widget.deleteLater()

    def _detach_effect_target(
        self,
        animation: QAbstractAnimation,
        effect: QGraphicsOpacityEffect | None,
    ) -> None:
        if effect is None:
            return
        if isinstance(animation, QPropertyAnimation):
            if animation.targetObject() is effect:
                animation.setTargetObject(None)
            return
        if isinstance(animation, QAnimationGroup):
            for index in range(animation.animationCount()):
                self._detach_effect_target(animation.animationAt(index), effect)

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
    QPropertyAnimation,
    QRect,
    QObject,
    QTimer,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget
from shiboken6 import delete as delete_qobject, isValid


class MotionDuration(IntEnum):
    FAST = 140
    NORMAL = 180
    EMPHASIS = 220


@dataclass(slots=True)
class _MotionState:
    widget: weakref.ReferenceType[QWidget]
    animation: QAbstractAnimation
    effect: QGraphicsOpacityEffect | None = None
    final_geometry: QRect | None = None
    final_maximum_height: int | None = None
    hide_on_finish: bool = False
    on_finished: Callable[[], None] | None = None
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
        parent = widget.parentWidget()
        if parent and parent.layout():
            parent.layout().activate()
        vertical_offset = 0 if self._is_layout_managed(widget) else 6
        self._fade(widget, MotionDuration.EMPHASIS, vertical_offset=vertical_offset)

    def retire(self, widget: QWidget, on_finished: Callable[[], None]) -> None:
        if self.reduce_motion or not widget.isVisible():
            widget.hide()
            on_finished()
            return
        key = id(widget)
        self._finish(key, stopped=True)
        parent = widget.parentWidget()
        if parent and parent.layout():
            parent.layout().activate()
        original_maximum_height = widget.maximumHeight()
        start_height = max(widget.height(), widget.sizeHint().height(), 1)
        widget.setMaximumHeight(start_height)
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
        opacity = QPropertyAnimation(effect, b"opacity", self)
        opacity.setDuration(int(MotionDuration.NORMAL))
        opacity.setStartValue(1.0)
        opacity.setEndValue(0.0)
        opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        height = QPropertyAnimation(widget, b"maximumHeight", self)
        height.setDuration(int(MotionDuration.NORMAL))
        height.setStartValue(start_height)
        height.setEndValue(0)
        height.setEasingCurve(QEasingCurve.Type.OutCubic)
        group = QParallelAnimationGroup(self)
        group.addAnimation(opacity)
        group.addAnimation(height)
        self._register(
            widget,
            group,
            effect=effect,
            final_maximum_height=original_maximum_height,
            hide_on_finish=True,
            on_finished=on_finished,
        )

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
        *,
        vertical_offset: int = 0,
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
        if vertical_offset:
            final_geometry = widget.geometry()
            start_geometry = final_geometry.translated(0, vertical_offset)
            widget.setGeometry(start_geometry)
            geometry = QPropertyAnimation(widget, b"geometry", self)
            geometry.setDuration(int(duration))
            geometry.setStartValue(start_geometry)
            geometry.setEndValue(final_geometry)
            geometry.setEasingCurve(QEasingCurve.Type.OutCubic)
            group = QParallelAnimationGroup(self)
            group.addAnimation(opacity)
            group.addAnimation(geometry)
            self._register(widget, group, effect=effect, final_geometry=final_geometry)
            return
        self._register(widget, opacity, effect=effect)

    def _register(
        self,
        widget: QWidget,
        animation: QAbstractAnimation,
        *,
        effect: QGraphicsOpacityEffect | None = None,
        final_geometry: QRect | None = None,
        final_maximum_height: int | None = None,
        hide_on_finish: bool = False,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        key = id(widget)
        state = _MotionState(
            weakref.ref(widget),
            animation,
            effect,
            final_geometry,
            final_maximum_height,
            hide_on_finish,
            on_finished,
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
                if state.final_geometry is not None:
                    widget.setGeometry(state.final_geometry)
                if state.final_maximum_height is not None:
                    widget.setMaximumHeight(state.final_maximum_height)
                if state.effect is not None:
                    state.effect.setOpacity(1.0)
                if state.hide_on_finish:
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
        if state.on_finished is not None:
            callback = state.on_finished
            state.on_finished = None
            callback()

    @staticmethod
    def _is_layout_managed(widget: QWidget) -> bool:
        parent = widget.parentWidget()
        return bool(parent and parent.layout() and parent.layout().indexOf(widget) >= 0)

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

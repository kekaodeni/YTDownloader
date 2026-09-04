"""Central, bounded motion for short Fluent-style state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, TYPE_CHECKING
import weakref

from PySide6.QtCore import (
    QAbstractAnimation,
    QAnimationGroup,
    QEasingCurve,
    QPropertyAnimation,
    QObject,
    QTimer,
    QSignalBlocker,
    Signal,
    QVariantAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget
from shiboken6 import delete as delete_qobject, isValid

if TYPE_CHECKING:
    from yt_downloader.ui.snapshot import SnapshotOverlay


@dataclass(frozen=True, slots=True)
class PresentationState:
    opacity: float = 1.0
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0

    def interpolate(self, other: "PresentationState", fraction: float) -> "PresentationState":
        return PresentationState(*(
            getattr(self, name) + (getattr(other, name) - getattr(self, name)) * fraction
            for name in ("opacity", "x", "y", "scale")
        ))


class AnimationController(QVariantAnimation):
    """One reusable timeline; retargeting starts at the presentation, not rest."""

    presentation_changed = Signal(object)

    def __init__(self, initial: PresentationState = PresentationState(), parent=None):
        super().__init__(parent)
        self.presentation = initial
        self._origin = initial
        self.target = initial
        self.valueChanged.connect(self._present)

    def retarget(self, target: PresentationState, *, duration: int, easing=QEasingCurve.Type.OutQuart):
        self.stop()
        self._origin = self.presentation
        self.target = target
        with QSignalBlocker(self):
            self.setStartValue(0.0)
            self.setEndValue(1.0)
            self.setDuration(max(1, int(duration)))
            self.setEasingCurve(easing)
            self.setCurrentTime(0)
        self._present(0.0)
        self.start()

    def _present(self, fraction):
        self.presentation = self._origin.interpolate(self.target, float(fraction))
        self.presentation_changed.emit(self.presentation)

    def cleanup(self):
        self.stop()

    def interrupt(self) -> PresentationState:
        self.stop()
        return self.presentation

    def reverse(self, *, duration: int):
        self.retarget(self._origin, duration=duration, easing=QEasingCurve.Type.InCubic)


class MotionTokens(IntEnum):
    PRESS = 90
    HOVER = 130
    FOCUS = 140
    STATE = 160
    PAGE = 210
    CARD_ENTER = 240
    CARD_REPOSITION = 240
    CARD_EXIT = 190
    THUMBNAIL = 200
    DIALOG_ENTER = 210
    DIALOG_EXIT = 150
    POPUP_ENTER = 180
    POPUP_EXIT = 130
    MENU_ENTER = 170
    MENU_EXIT = 130
    SCROLL = 160
    REDUCED = 90


@dataclass(slots=True)
class _MotionState:
    widget: weakref.ReferenceType[QWidget]
    animation: QAbstractAnimation
    effect: QGraphicsOpacityEffect | None = None
    dispose_widget: bool = False
    finishing: bool = False
    disposed: bool = False
    destroyed_handler: Callable | None = None


class MotionManager(QObject):
    def __init__(self, reduce_motion: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.reduce_motion = reduce_motion
        self._active: dict[int, _MotionState] = {}
        self._snapshots: dict[int, SnapshotOverlay] = {}

    @property
    def active_count(self) -> int:
        self._discard_finished_snapshots()
        return len(self._active) + len(self._snapshots)

    def set_reduce_motion(self, enabled: bool) -> None:
        self.reduce_motion = bool(enabled)
        if self.reduce_motion:
            for key in tuple(self._active):
                self._finish(key, stopped=True)
            for proxy in tuple(self._snapshots.values()):
                if isValid(proxy):
                    proxy.cleanup()
            self._snapshots.clear()

    def switch_page(self, stack: QStackedWidget, index: int) -> None:
        if not 0 <= index < stack.count():
            return
        changed = stack.currentIndex() != index
        if self.reduce_motion or not changed:
            stack.setCurrentIndex(index)
            return
        from yt_downloader.ui.snapshot import SnapshotOverlay, capture_visible

        key = id(stack)
        previous = self._snapshots.get(key)
        source = previous if previous is not None and isValid(previous) else stack.currentWidget()
        before = capture_visible(source)
        if previous is not None and isValid(previous):
            previous.cleanup()
        self._snapshots.pop(key, None)
        stack.setCurrentIndex(index)
        target = stack.widget(index)
        after = capture_visible(target)
        if before is None or after is None:
            if before is not None:
                before.release()
            if after is not None:
                after.release()
            return
        proxy = SnapshotOverlay(stack, before, geometry=target.geometry(), next_frame=after)
        self._snapshots[key] = proxy
        proxy.finished.connect(self._discard_finished_snapshots)
        proxy.play(PresentationState(opacity=0, x=-4, scale=1), duration=MotionTokens.PAGE)

    def reveal(self, widget: QWidget) -> None:
        widget.show()
        if self.reduce_motion:
            return
        self._fade(widget, MotionTokens.CARD_ENTER)

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
        def mutate() -> None:
            widget.hide()
            on_finished()

        self.transition_layout(parent, mutate)

    def transition_layout(self, host: QWidget, mutate: Callable[[], None]) -> None:
        """Commit business/layout changes once; animate only the old presentation."""
        from yt_downloader.ui.snapshot import SnapshotOverlay, capture_visible

        before = None if self.reduce_motion else capture_visible(host)
        old = self._snapshots.pop(id(host), None)
        if old is not None and isValid(old):
            old.cleanup()
        try:
            mutate()
            ancestor = host
            while ancestor is not None:
                if ancestor.layout():
                    ancestor.layout().activate()
                ancestor = ancestor.parentWidget()
        except Exception:
            if before:
                before.release()
            raise
        if before is None:
            return
        if not host.isVisible():
            before.release()
            return
        proxy = SnapshotOverlay(host, before)
        self._snapshots[id(host)] = proxy
        proxy.finished.connect(self._discard_finished_snapshots)
        proxy.play(PresentationState(opacity=0, y=-5), duration=MotionTokens.CARD_EXIT,
                   easing=QEasingCurve.Type.InCubic)

    def _discard_finished_snapshots(self) -> None:
        self._snapshots = {
            key: proxy for key, proxy in self._snapshots.items()
            if isValid(proxy) and not proxy.finished_once
        }

    def feedback(self, widget: QWidget) -> None:
        if self.reduce_motion or not widget.isVisible():
            return
        key = id(widget)
        self._finish(key, stopped=True)
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(int(MotionTokens.PRESS))
        animation.setStartValue(1.0)
        animation.setKeyValueAt(0.35, 0.82)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._register(widget, animation, effect=effect)

    def _fade(
        self,
        widget: QWidget,
        duration: MotionTokens,
    ) -> None:
        key = id(widget)
        state = self._active.get(key)
        if state and not state.finishing and isinstance(state.animation, AnimationController):
            state.animation.retarget(PresentationState(), duration=int(duration))
            return
        self._finish(key, stopped=True)
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        opacity = AnimationController(PresentationState(opacity=0.0), self)
        opacity.presentation_changed.connect(
            lambda value: effect.setOpacity(value.opacity) if isValid(effect) else None
        )
        opacity.retarget(PresentationState(), duration=int(duration))
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
        state.destroyed_handler = lambda: self._schedule_finish(key, state)
        widget.destroyed.connect(state.destroyed_handler)
        animation.finished.connect(lambda current=key, value=state: self._schedule_finish(current, value))
        if animation.state() != QAbstractAnimation.State.Running:
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
        if state.disposed:
            return
        state.disposed = True
        if isValid(state.animation):
            state.animation.stop()
        widget = state.widget()
        if widget is not None and isValid(widget):
            widget.destroyed.disconnect(state.destroyed_handler)
            if state.effect is not None and isValid(state.effect):
                state.effect.setOpacity(1.0)
            if state.dispose_widget:
                widget.hide()
        if isValid(state.animation):
            self._detach_effect_target(state.animation, state.effect)
            delete_qobject(state.animation)
        if widget is not None and isValid(widget):
            if state.effect is not None and widget.graphicsEffect() is state.effect:
                widget.setGraphicsEffect(None)
        if self._active.get(key) is state:
            self._active.pop(key, None)
        if state.dispose_widget and widget is not None and isValid(widget):
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

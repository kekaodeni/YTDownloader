import pytest
from PySide6.QtCore import QEasingCurve

from yt_downloader.ui.motion import AnimationController, PresentationState


def test_retarget_preserves_presentation_instead_of_restarting(qapp):
    controller = AnimationController(PresentationState(opacity=0, y=8, scale=0.99))
    controller.retarget(PresentationState(), duration=240, easing=QEasingCurve.Type.Linear)
    controller.setCurrentTime(120)
    halfway = controller.presentation
    assert halfway.opacity == pytest.approx(0.5)
    assert halfway.y == pytest.approx(4)

    controller.retarget(PresentationState(opacity=0, y=-5, scale=0.985), duration=190)

    assert controller.presentation == halfway
    controller.setCurrentTime(190)
    assert controller.presentation == PresentationState(opacity=0, y=-5, scale=0.985)
    controller.cleanup()


def test_interrupted_animation_can_reverse_from_its_current_position(qapp):
    initial = PresentationState(opacity=0, y=8)
    controller = AnimationController(initial)
    controller.retarget(PresentationState(), duration=240, easing=QEasingCurve.Type.Linear)
    controller.setCurrentTime(60)
    current = controller.interrupt()
    assert current.opacity == pytest.approx(0.25)
    controller.reverse(duration=90)
    assert controller.presentation == current
    controller.setCurrentTime(90)
    assert controller.presentation == initial
    controller.cleanup()


def test_revealing_an_animating_widget_reuses_its_current_opacity(qtbot):
    from PySide6.QtWidgets import QLabel
    from yt_downloader.ui.motion import MotionManager

    card = QLabel("连续显示")
    qtbot.addWidget(card)
    card.show()
    manager = MotionManager()
    manager.reveal(card)
    qtbot.wait(60)
    effect = card.graphicsEffect()
    before = effect.opacity()
    assert 0 < before < 1

    manager.reveal(card)

    assert card.graphicsEffect() is effect
    assert effect.opacity() == pytest.approx(before)
    assert manager.active_count == 1
    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1000)
    assert card.graphicsEffect() is None


def test_destroying_target_releases_its_channel_without_waiting_for_duration(qapp, qtbot):
    from PySide6.QtWidgets import QLabel
    from shiboken6 import delete
    from yt_downloader.ui.motion import MotionManager

    manager = MotionManager()
    card = QLabel("temporary")
    card.show()
    manager.reveal(card)
    delete(card)
    qapp.processEvents()
    assert manager.active_count == 0

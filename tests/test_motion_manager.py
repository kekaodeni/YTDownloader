from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from yt_downloader.ui.motion import MotionDuration, MotionManager
from yt_downloader.ui.theme import DARK, LIGHT, _qss


def test_motion_durations_are_short_and_semantic() -> None:
    assert tuple(int(value) for value in MotionDuration) == (140, 180, 220)


def test_glass_inspired_surfaces_are_static_tints_without_blur_or_animated_shadow(qapp) -> None:
    for tokens in (LIGHT, DARK):
        stylesheet = _qss(tokens).lower()
        assert tokens.surface_tint.lower() in stylesheet
        assert tokens.surface_highlight.lower() in stylesheet
        assert "blur" not in stylesheet
        assert "box-shadow" not in stylesheet


def test_page_and_card_animations_remove_effects_after_finishing(qtbot) -> None:
    stack = QStackedWidget()
    first = QWidget()
    second = QWidget()
    stack.addWidget(first)
    stack.addWidget(second)
    qtbot.addWidget(stack)
    stack.show()
    manager = MotionManager(reduce_motion=False)

    manager.switch_page(stack, 1)

    assert stack.currentIndex() == 1
    assert second.graphicsEffect() is not None
    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1000)
    assert second.graphicsEffect() is None

    card = QLabel("card", stack)
    manager.reveal(card)
    assert card.isVisible()
    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1000)
    assert card.graphicsEffect() is None


def test_reduce_motion_stops_active_effects_and_future_switches_are_immediate(qtbot) -> None:
    stack = QStackedWidget()
    first = QWidget()
    second = QWidget()
    stack.addWidget(first)
    stack.addWidget(second)
    qtbot.addWidget(stack)
    stack.show()
    manager = MotionManager(reduce_motion=False)
    manager.switch_page(stack, 1)
    assert manager.active_count == 1

    manager.set_reduce_motion(True)

    assert manager.active_count == 0
    assert second.graphicsEffect() is None
    manager.switch_page(stack, 0)
    assert stack.currentIndex() == 0
    assert manager.active_count == 0


def test_repeated_page_switches_do_not_accumulate_animation_objects(qtbot) -> None:
    stack = QStackedWidget()
    pages = [QWidget() for _ in range(3)]
    for page in pages:
        stack.addWidget(page)
    qtbot.addWidget(stack)
    stack.show()
    manager = MotionManager(reduce_motion=False)

    for index in range(60):
        manager.switch_page(stack, index % 3)

    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1500)
    assert all(page.graphicsEffect() is None for page in pages)

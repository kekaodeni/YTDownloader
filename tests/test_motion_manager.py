from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from yt_downloader.ui.motion import MotionTokens, MotionManager
from yt_downloader.ui.theme import DARK, LIGHT, _qss


def test_motion_durations_are_short_and_semantic() -> None:
    assert (MotionTokens.PRESS, MotionTokens.HOVER, MotionTokens.FOCUS) == (90, 130, 140)
    assert (MotionTokens.STATE, MotionTokens.PAGE, MotionTokens.CARD_ENTER) == (160, 210, 240)
    assert (MotionTokens.CARD_EXIT, MotionTokens.THUMBNAIL) == (190, 200)
    assert (MotionTokens.DIALOG_ENTER, MotionTokens.DIALOG_EXIT) == (210, 150)
    assert (MotionTokens.POPUP_ENTER, MotionTokens.POPUP_EXIT) == (180, 130)
    assert (MotionTokens.MENU_ENTER, MotionTokens.MENU_EXIT, MotionTokens.SCROLL) == (170, 130, 160)


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
    assert manager.active_count == 1
    assert second.graphicsEffect() is None
    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1000)
    assert second.graphicsEffect() is None

    card = QLabel("card", stack)
    manager.reveal(card)
    assert card.isVisible()
    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1000)
    assert card.graphicsEffect() is None


def test_retire_uses_overlay_without_animating_real_layout_geometry(qapp, qtbot) -> None:
    host = QWidget()
    layout = QVBoxLayout(host)
    first = QLabel("first")
    second = QLabel("second")
    first.setMinimumHeight(80)
    second.setMinimumHeight(80)
    layout.addWidget(first)
    layout.addWidget(second)
    qtbot.addWidget(host)
    host.resize(320, 240)
    host.show()
    qapp.processEvents()
    original_maximum_height = first.maximumHeight()
    second_start = second.geometry().top()
    completed = []
    manager = MotionManager(reduce_motion=False)

    manager.retire(first, lambda: completed.append(True))

    qapp.processEvents()
    assert completed == [True]
    assert first.maximumHeight() == original_maximum_height
    assert first.graphicsEffect() is None
    assert manager.active_count == 1
    assert second.geometry().top() < second_start
    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1000)
    qapp.processEvents()
    assert first.graphicsEffect() is None
    assert first.maximumHeight() == original_maximum_height


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

    for index in range(100):
        manager.switch_page(stack, index % 3)

    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=1500)
    assert all(page.graphicsEffect() is None for page in pages)


def test_repeated_task_retirement_releases_every_snapshot_proxy(qapp, qtbot) -> None:
    host = QWidget()
    layout = QVBoxLayout(host)
    qtbot.addWidget(host)
    host.resize(320, 240)
    host.show()
    manager = MotionManager(reduce_motion=False)

    for index in range(100):
        card = QLabel(f"card {index}")
        card.setMinimumHeight(24)
        layout.addWidget(card)
        qapp.processEvents()

        def remove(current=card) -> None:
            layout.removeWidget(current)
            current.deleteLater()

        manager.retire(card, remove)

    qtbot.waitUntil(lambda: manager.active_count == 0, timeout=2000)
    qapp.processEvents()
    assert manager.active_count == 0

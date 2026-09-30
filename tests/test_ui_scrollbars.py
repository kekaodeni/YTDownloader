from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
import pytest
from conftest import find_item, run_frames


def scrollbar_for(view):
    return next(child for child in view.childItems() if child.inherits('QQuickScrollBar'))


def test_scroll_activity_lingers_then_returns_to_idle(quick_window, qapp, tmp_path):
    from test_quick_scroll import prepare, wheel
    view = prepare(quick_window, qapp, tmp_path)
    bar = scrollbar_for(view)
    QTest.mouseMove(quick_window.root, QPointF(0, 0).toPoint())
    wheel(quick_window, view, -120)
    run_frames(qapp, 260)
    assert bar.property('recentActivity')
    assert bar.property('restingThumbOpacity') >= .49
    run_frames(qapp, 1150)
    assert not bar.property('recentActivity')
    assert bar.property('restingThumbOpacity') == .28


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_scrollbar_has_fixed_hit_area_and_never_shifts_content_on_hover(quick_window, qapp, theme):
    quick_window._select_page(2)
    quick_window.settings_page.selectCategory(1)
    quick_window.theme.set_mode(theme)
    run_frames(qapp)
    scroll = find_item(quick_window, 'settingsScroll')
    bar = scrollbar_for(scroll)
    assert bar.width() == 12
    width = scroll.width()
    QTest.mouseMove(quick_window.root, QPointF(0, 0).toPoint())
    run_frames(qapp, 40)
    QTest.mouseMove(quick_window.root, bar.mapToScene(QPointF(6, bar.height()/2)).toPoint())
    run_frames(qapp, 200)
    assert scroll.width() == width
    assert bar.property('thumbWidth') == pytest.approx(6, abs=.01)


@pytest.mark.parametrize('reduced', [False, True])
def test_scrollbar_drag_minimum_auto_hide_and_keyboard(quick_window, qapp, reduced):
    quick_window._select_page(2)
    quick_window.settings_page.selectCategory(1)
    quick_window.settings_page.setSetting('reduce_motion', reduced)
    run_frames(qapp)
    scroll = find_item(quick_window, 'settingsScroll')
    bar = scrollbar_for(scroll)
    scroll.setProperty('contentHeight', 20000)
    run_frames(qapp, 60)
    thumb = bar.property('contentItem')
    assert thumb.height() >= 35.9
    point = thumb.mapToScene(QPointF(thumb.width()/2, thumb.height()/2)).toPoint()
    QTest.mousePress(quick_window.root, Qt.LeftButton, Qt.NoModifier, point)
    run_frames(qapp, 40)
    assert bar.property('pressed')
    assert bar.property('thumbWidth') == 7
    QTest.mouseMove(quick_window.root, point + QPointF(0, 120).toPoint())
    run_frames(qapp, 40)
    QTest.mouseRelease(quick_window.root, Qt.LeftButton, Qt.NoModifier, point + QPointF(0,120).toPoint())
    assert scroll.property('contentY') > 0
    scroll.forceActiveFocus()
    QTest.keyClick(quick_window.root, Qt.Key_Home)
    assert scroll.property('contentY') == 0
    QTest.keyClick(quick_window.root, Qt.Key_PageDown)
    assert scroll.property('contentY') == scroll.height()
    QTest.keyClick(quick_window.root, Qt.Key_End)
    assert abs(scroll.property('contentY') - (20000 - scroll.height())) < 1
    scroll.setProperty('contentHeight', 20)
    run_frames(qapp, 100)
    assert not bar.isVisible()

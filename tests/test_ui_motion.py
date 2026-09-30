"""Motion continuity through stable real Qt Quick component instances."""
from PySide6.QtCore import QTimer, QPointF
import pytest
from conftest import find_item, run_frames, click_item


def test_settings_category_crossfade_keeps_both_instances_visible(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    old = find_item(quick_window, 'settingsCategory-0')
    new = find_item(quick_window, 'settingsCategory-2')
    quick_window.settings_page.selectCategory(2)
    run_frames(qapp, 60)
    assert old.isVisible() and new.isVisible()
    run_frames(qapp, 250)
    assert not old.isVisible() and new.isVisible()
    assert old is find_item(quick_window, 'settingsCategory-0')


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('reduced', [False, True])
def test_settings_navigation_never_has_blank_frame_and_preserves_scroll(quick_window, qapp, theme, reduced):
    quick_window.theme.set_mode(theme)
    quick_window.settings_page.setSetting('reduce_motion', reduced)
    assert quick_window.state['reduceMotion'] == reduced
    assert quick_window.motion.property('reduced') == reduced
    quick_window.root.resize(700, 560)
    quick_window._select_page(2)
    quick_window.settings_page.selectCategory(1)
    run_frames(qapp)
    first_scroll = find_item(quick_window, 'settingsScroll')
    first_scroll.setProperty('contentY', 120)
    run_frames(qapp, 80)
    offset = first_scroll.property('contentY')
    hosts = [find_item(quick_window, f'settingsHost-{n}') for n in range(6)]
    nav = find_item(quick_window, 'settingsNavigation')
    nav_position = nav.mapToScene(QPointF())
    observations = []
    timer = QTimer()
    def capture():
        assert not quick_window.grab().isNull()
        observations.append([h.opacity() for h in hosts])
        assert max(h.opacity() for h in hosts) >= .45
        assert nav.mapToScene(QPointF()) == nav_position
        if reduced:
            assert all(h.property('visualOffset') == 0 for h in hosts)
    timer.timeout.connect(capture)
    timer.start(8)
    try:
        for n in (2, 3, 4, 5, 0, 1):
            quick_window.settings_page.selectCategory(n)
            run_frames(qapp, 40)
            # A transparent-black color endpoint creates a dark flash while
            # the selected secondary-navigation background is interpolating.
            nav_background = find_item(quick_window, 'settingsNavigation-selection')
            assert nav_background.property('color').alpha() == 255
            run_frames(qapp, 220)
            assert hosts[n].isEnabled()
            assert all(not h.isEnabled() for i, h in enumerate(hosts) if i != n)
        assert abs(first_scroll.property('contentY') - offset) < 1
    finally:
        timer.stop()
    assert observations
    if not reduced:
        assert any(sum(.05 < alpha < .95 for alpha in frame) == 2 for frame in observations)


@pytest.mark.parametrize('reduced', [False, True])
def test_main_navigation_keeps_stable_instances_and_motion_policy(quick_window, qapp, reduced):
    quick_window.settings_page.setSetting('reduce_motion', reduced)
    hosts = [find_item(quick_window, f'pageHost-{n}') for n in range(4)]
    for n in (1, 2, 3, 0):
        quick_window._select_page(n)
        run_frames(qapp, 60)
        assert max(h.opacity() for h in hosts) >= .45
        run_frames(qapp, 240)
        assert hosts[n].opacity() == 1
        assert hosts[n] is find_item(quick_window, f'pageHost-{n}')


def test_popup_and_modal_use_short_fade_without_changing_focus_contract(quick_window, qapp):
    from PySide6.QtCore import QMetaObject
    quick_window._select_page(2)
    quick_window.settings_page.selectCategory(1)
    run_frames(qapp)
    combo = find_item(quick_window, 'defaultDownloadProfile')
    click_item(quick_window, combo)
    popup = find_item(quick_window, 'popup-defaultDownloadProfile')
    run_frames(qapp, 40)
    assert 0 < popup.property('opacity') < 1
    run_frames(qapp, 180)
    assert popup.property('opacity') == 1
    assert QMetaObject.invokeMethod(popup, 'close')
    run_frames(qapp, 200)
    session = quick_window.dialogs.info('Cookie', 'Cookie')
    run_frames(qapp, 50)
    dialog = find_item(quick_window, 'dialog-info')
    assert 0 < dialog.property('opacity') < 1
    run_frames(qapp, 200)
    assert dialog.property('opacity') == 1
    session.reject()
    run_frames(qapp, 250)

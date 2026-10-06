from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
import pytest

from conftest import click_item, find_item, run_frames


@pytest.mark.parametrize('edge', ['top', 'bottom'])
@pytest.mark.parametrize('pixels', [False, True])
def test_twenty_outward_wheel_events_finish_one_smooth_edge_pulse(quick_window, qapp, edge, pixels):
    import time
    from PySide6.QtCore import QTimer
    from test_quick_scroll import wheel
    quick_window._select_page(3)
    quick_window.settings_page.setSetting('language', 'ja-JP')
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    click_item(quick_window, combo)
    run_frames(qapp, 180)
    popup = find_item(quick_window, 'popup-languageCombo')
    view = find_item(quick_window, 'options-languageCombo')
    bar = next(x for x in view.childItems() if x.inherits('QQuickScrollBar'))
    top = view.property('originY')
    bottom = top + max(0, view.property('contentHeight')-view.height())
    view.setProperty('contentY', top if edge == 'top' else bottom)
    run_frames(qapp, 180)
    direction = 1 if edge == 'top' else -1
    baseline = (popup.property('x'), popup.property('y'), popup.property('width'), popup.property('height'),
                bar.x(), bar.y(), bar.width(), bar.height(), bar.property('size'), bar.property('position'),
                combo.property('model'), combo.property('currentIndex'))
    observations = []
    sent = []
    started = time.perf_counter()
    def tick():
        if len(sent) < 20:
            wheel(quick_window, view, angle=0 if pixels else direction*120,
                  pixels=direction*10 if pixels else 0)
            sent.append(time.perf_counter()-started)
        observations.append((time.perf_counter()-started,
                             direction*(view.property('contentItem').mapToItem(view, QPointF()).y()+view.property('contentY')),
                             view.property('contentY'),
                             (popup.property('x'), popup.property('y'), popup.property('width'), popup.property('height'),
                              bar.x(), bar.y(), bar.width(), bar.height(), bar.property('size'), bar.property('position'),
                              combo.property('model'), combo.property('currentIndex'))))
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(4)
    try:
        run_frames(qapp, 260)
    finally:
        timer.stop()
    assert len(sent) == 20
    assert sent[-1] < .14  # Entire burst fits within the 150ms pulse.
    assert observations[0][1] < .2  # Rise gently, never jump directly to the peak.
    assert 3.5 <= max(x[1] for x in observations) <= 4.01
    peak = max(observations, key=lambda x: x[1])
    assert .035 <= peak[0] <= .085
    decay = [x[1] for x in observations if .085 <= x[0] <= .18]
    assert all(b <= a+.02 for a, b in zip(decay, decay[1:]))
    assert all(abs(x[1]) < .1 for x in observations if x[0] >= .18)
    assert all(top-.01 <= x[2] <= bottom+.01 and x[3] == baseline for x in observations)


def test_edge_feedback_rearms_after_finish_direction_change_or_leaving_edge(quick_window, qapp):
    from test_quick_scroll import wheel
    quick_window._select_page(3)
    run_frames(qapp)
    click_item(quick_window, find_item(quick_window, 'languageCombo'))
    run_frames(qapp, 180)
    view = find_item(quick_window, 'options-languageCombo')
    top = view.property('originY')
    view.setProperty('contentY', top)

    wheel(quick_window, view, angle=120)
    run_frames(qapp, 45)
    assert view.property('elasticOffset') > 3
    before = view.property('elasticOffset')
    wheel(quick_window, view, angle=120)
    assert view.property('elasticOffset') == before
    wheel(quick_window, view, angle=-120)
    assert view.property('elasticOffset') == 0
    language_wheel(quick_window, view, pixels=-24, native=True)
    run_frames(qapp, 250)
    assert view.property('contentY') > top
    view.setProperty('contentY', top)
    wheel(quick_window, view, angle=120)
    run_frames(qapp, 35)
    assert view.property('elasticOffset') > 1
    view.setProperty('contentY', top+20)
    assert view.property('elasticOffset') == 0
    view.setProperty('contentY', top)
    wheel(quick_window, view, angle=120)
    run_frames(qapp, 180)
    assert view.property('elasticOffset') == 0
    wheel(quick_window, view, angle=120)
    run_frames(qapp, 45)
    assert view.property('elasticOffset') > 3
    quick_window.settings_page.setSetting('reduce_motion', True)
    assert view.property('elasticOffset') == 0
    wheel(quick_window, view, angle=120)
    run_frames(qapp, 60)
    assert view.property('elasticOffset') == 0


def language_wheel(window, item, angle=0, pixels=0, native=False):
    import time
    from PySide6.QtCore import QCoreApplication, QPoint
    from PySide6.QtGui import QWheelEvent, QInputDevice, QPointingDevice
    from test_quick_scroll import wheel
    if not pixels:
        wheel(window, item, angle=angle)
        return
    local = item.mapToScene(QPointF(item.width()/2, item.height()/2))
    global_pos = QPointF(window.root.mapToGlobal(local.toPoint()))
    QTest.mouseMove(window.root, local.toPoint())
    device = QPointingDevice('test touchpad', 42, QInputDevice.TouchPad, QPointingDevice.Finger,
                             QInputDevice.Position | QInputDevice.PixelScroll, 1, 0)
    # Exercise both window delivery (visual pulse) and the native Flickable
    # pixel path. Window delivery may coalesce synthetic touchpad phases.
    for phase in (Qt.ScrollBegin, Qt.ScrollUpdate, Qt.ScrollUpdate, Qt.ScrollUpdate, Qt.ScrollUpdate, Qt.ScrollEnd):
        position = QPointF(item.width()/2, item.height()/2) if native else local
        event = QWheelEvent(position, global_pos, QPoint(0, pixels if phase == Qt.ScrollUpdate else 0),
                            QPoint(), Qt.NoButton, Qt.NoModifier, phase, False,
                            Qt.MouseEventSynthesizedBySystem, device)
        event.setTimestamp(int(time.monotonic()*1000))
        QCoreApplication.sendEvent(item if native else window.root, event)
        run_frames(QCoreApplication.instance(), 12)


@pytest.mark.parametrize('velocity', [2200., -2200.])
def test_language_native_inertia_cannot_expose_large_blank_region(quick_window, qapp, velocity):
    from PySide6.QtCore import QMetaObject, Q_ARG, QTimer
    quick_window._select_page(3)
    run_frames(qapp)
    click_item(quick_window, find_item(quick_window, 'languageCombo'))
    run_frames(qapp, 160)
    view = find_item(quick_window, 'options-languageCombo')
    top = view.property('originY')
    bottom = top + max(0, view.property('contentHeight')-view.height())
    view.setProperty('contentY', top if velocity > 0 else bottom)
    positions = []
    timer = QTimer()
    timer.timeout.connect(lambda: positions.append(view.property('contentY')))
    timer.start(5)
    try:
        assert QMetaObject.invokeMethod(view, 'flick', Q_ARG(float, 0.), Q_ARG(float, velocity))
        run_frames(qapp, 420)
    finally:
        timer.stop()
    assert positions
    assert min(positions) >= top-10
    assert max(positions) <= bottom+10


def test_keyboard_selection_without_opening_popup_refreshes_locale(quick_window, qapp):
    quick_window._select_page(3)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    combo.forceActiveFocus()
    QTest.keyClick(quick_window.root, Qt.Key_Down)
    run_frames(qapp, 120)
    assert quick_window.i18n.currentLocale == 'zh-TW'
    assert not find_item(quick_window, 'popup-languageCombo').property('visible')


@pytest.mark.parametrize('mode', ['light', 'dark'])
@pytest.mark.parametrize('reduced', [False, True])
def test_all_languages_have_bounded_non_accumulating_wheel_feedback(quick_window, qapp, mode, reduced):
    quick_window._select_page(3)
    quick_window.theme.set_mode(mode)
    quick_window.settings_page.setSetting('reduce_motion', reduced)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    names = [x['name'] for x in quick_window.i18n.languages]
    for locale in quick_window.i18n.languages:
        quick_window.settings_page.setSetting('language', locale['locale'])
        click_item(quick_window, combo)
        run_frames(qapp, 160)
        popup = find_item(quick_window, 'popup-languageCombo')
        view = find_item(quick_window, 'options-languageCombo')
        geometry = (popup.property('height'), view.height(), view.property('contentHeight'))
        top = view.property('originY')
        bottom = top + max(0, view.property('contentHeight')-view.height())
        for edge, delta in ((top, 720), (bottom, -720)):
            view.setProperty('contentY', edge)
            for _ in range(12):
                language_wheel(quick_window, view, angle=delta if _ % 2 == 0 else 0,
                      pixels=0 if _ % 2 == 0 else (40 if delta > 0 else -40))
                offset = view.property('elasticOffset')
                assert offset == 0 if reduced else 0 <= offset * (1 if delta > 0 else -1) <= 4
                run_frames(qapp, 8)
                y = view.property('contentY')
                assert top-10 <= y <= bottom+10
                translation = view.property('contentItem').mapToItem(view, QPointF()).y()+y
                assert abs(translation) <= 4.01
                if reduced:
                    assert abs(translation) < .01
                assert (popup.property('height'), view.height(), view.property('contentHeight')) == geometry
                assert combo.property('model') == names
            run_frames(qapp, 240)
            assert view.property('contentY') == pytest.approx(edge, abs=.01)
            assert view.property('contentItem').mapToItem(view, QPointF()).y()+view.property('contentY') == pytest.approx(0, abs=.01)
            start = view.mapToScene(QPointF(view.width()/2, view.height()/2)).toPoint()
            direction = 1 if edge == top else -1
            QTest.mousePress(quick_window.root, Qt.LeftButton, Qt.NoModifier, start)
            try:
                QTest.mouseMove(quick_window.root, start + QPointF(0, direction*30).toPoint())
                run_frames(qapp, 30)
                QTest.mouseMove(quick_window.root, start + QPointF(0, direction*120).toPoint())
                run_frames(qapp, 30)
                assert top-10 <= view.property('contentY') <= bottom+10
            finally:
                QTest.mouseRelease(quick_window.root, Qt.LeftButton, Qt.NoModifier, start + QPointF(0, direction*120).toPoint())
            run_frames(qapp, 220)
        QTest.keyClick(quick_window.root, Qt.Key_Escape)
        run_frames(qapp, 160)


@pytest.mark.parametrize('subtle', [False, True])
@pytest.mark.parametrize('pixels', [0, -24])
def test_language_wheel_still_scrolls_inside_native_bounds(quick_window, qapp, subtle, pixels):
    quick_window._select_page(3)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    combo.setProperty('subtleOverscroll', subtle)
    click_item(quick_window, combo)
    run_frames(qapp, 160)
    view = find_item(quick_window, 'options-languageCombo')
    view.setProperty('contentY', view.property('originY'))
    language_wheel(quick_window, view, pixels=pixels, angle=0 if pixels else -120, native=True)
    run_frames(qapp, 160)
    assert view.property('contentY') > view.property('originY')
    assert view.property('elasticOffset') == 0


def test_keyboard_type_search_reveals_option_without_hover_scrolling(quick_window, qapp):
    quick_window._select_page(3)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    click_item(quick_window, combo)
    run_frames(qapp, 160)
    QTest.keyClick(quick_window.root, Qt.Key_P)
    run_frames(qapp, 100)
    view = find_item(quick_window, 'options-languageCombo')
    option = find_item(quick_window, 'languageCombo-option-7')
    y = option.mapToItem(view, QPointF()).y()
    assert 0 <= y <= view.height()-option.height()+1
    QTest.keyClick(quick_window.root, Qt.Key_Return)
    run_frames(qapp, 220)
    assert quick_window.i18n.currentLocale == 'pt-BR'


def test_language_hover_does_not_reposition_or_change_popup(quick_window, qapp):
    quick_window._select_page(3)
    quick_window.settings_page.setSetting('language', 'th-TH')
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    click_item(quick_window, combo)
    run_frames(qapp, 220)
    popup = find_item(quick_window, 'popup-languageCombo')
    view = popup.property('contentItem')
    before = view.property('contentY')
    languages = quick_window.i18n.languages
    for dy in (1, 12, 90, 180, 40, 210, 1):
        point = view.mapToScene(QPointF(30, dy)).toPoint()
        QTest.mouseMove(quick_window.root, point)
        run_frames(qapp, 40)
        assert view.property('contentY') == before
        assert combo.property('count') == 10
        assert combo.property('currentIndex') == 9
        assert quick_window.i18n.languages == languages


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_all_ten_languages_can_be_selected_and_reopened_with_native_names(quick_window, qapp, mode):
    quick_window._select_page(3)
    quick_window.theme.set_mode(mode)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    languages = quick_window.i18n.languages
    names = [language['name'] for language in languages]
    for index, language in enumerate(languages):
        click_item(quick_window, combo)
        run_frames(qapp, 160)
        assert combo.property('model') == names
        QTest.keyClick(quick_window.root, Qt.Key_Home)
        for _ in range(index):
            QTest.keyClick(quick_window.root, Qt.Key_Down)
        run_frames(qapp, 80)
        view = find_item(quick_window, 'options-languageCombo')
        item = find_item(quick_window, f'languageCombo-option-{index}')
        y = item.mapToItem(view, QPointF()).y()
        assert -1 <= y <= view.height() - item.height() + 1
        QTest.keyClick(quick_window.root, Qt.Key_Return)
        run_frames(qapp, 220)
        assert quick_window.i18n.currentLocale == language['locale']
        assert combo.property('model') == names


def test_language_refresh_waits_until_popup_finishes_closing(quick_window, qapp):
    quick_window._select_page(3)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    click_item(quick_window, combo)
    run_frames(qapp, 180)
    QTest.keyClick(quick_window.root, Qt.Key_Down)
    QTest.keyClick(quick_window.root, Qt.Key_Return)
    assert quick_window.i18n.currentLocale == 'zh-CN'
    run_frames(qapp, 240)
    assert quick_window.i18n.currentLocale == 'zh-TW'
    assert not find_item(quick_window, 'popup-languageCombo').property('visible')

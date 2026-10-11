"""Native Qt input regressions for the installation guide's own viewport."""

import json

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QTest

from conftest import click_item, find_item, run_frames
from test_browser_onboarding import isolated_manager, open_browser, reveal
from test_quick_scroll import wheel
from yt_downloader.core.models import SUPPORTED_LOCALES


def guide_viewport(window):
    dialog = find_item(window, 'dialog-browser_guide')
    scroll = dialog.property('contentItem')
    flickable = scroll.property('contentItem')
    assert flickable.inherits('QQuickFlickable')
    return dialog, scroll, flickable


def open_guide(window, app, tmp_path, browser='chrome'):
    isolated_manager(window, tmp_path)
    open_browser(window, app, browser)
    entry = find_item(window, 'browser-install-guide')
    background = reveal(window, app, entry)
    click_item(window, entry)
    run_frames(app, 250)
    dialog, scroll, flickable = guide_viewport(window)
    assert dialog.property('opened') and flickable.height() > 0
    return dialog, scroll, flickable, background


def bounds(flickable):
    lower = flickable.property('originY')
    upper = lower + max(0, flickable.property('contentHeight') - flickable.height())
    return lower, upper


def qml_number(window, item, property_name):
    expression = QQmlExpression(window.engine.rootContext(), item,
                               'Number(' + property_name + ')')
    value, undefined = expression.evaluate()
    assert not undefined and not expression.hasError()
    return value


def geometry(item):
    if hasattr(item, 'mapToScene'):
        point = item.mapToScene(QPointF(0, 0))
        return (point.x(), point.y(), item.width(), item.height())
    return tuple(item.property(name) for name in ('x', 'y', 'width', 'height'))


def vertical_bar(scroll):
    bars = [item for item in scroll.childItems()
            if item.inherits('QQuickScrollBar') and item.objectName() == 'uiScrollBar']
    assert len(bars) == 1
    return bars[0]


def bar_geometry(bar):
    return geometry(bar) + (bar.property('size'), bar.property('position'),
                            bar.property('contentItem').width(),
                            bar.property('contentItem').height())


def edge_measurements(window, app, flickable, edge, count=30, pixels=0, bar=None):
    lower, upper = bounds(flickable)
    flickable.setProperty('contentY', lower if edge == 'top' else upper)
    run_frames(app, 240)
    values = []
    scrollbar_before = bar_geometry(bar) if bar else None
    scrollbar_stable = True
    direction = 1 if edge == 'top' else -1
    for _ in range(count):
        wheel(window, flickable, angle=direction * 240 if not pixels else 0,
              pixels=direction * pixels)
        values.append(flickable.property('contentY'))
        run_frames(app, 16)
        values.append(flickable.property('contentY'))
        if bar:
            scrollbar_stable &= bar_geometry(bar) == scrollbar_before
    run_frames(app, 240)
    values.append(flickable.property('contentY'))
    return {'edge': edge, 'bounds': [lower, upper],
            'minContentY': min(values), 'maxContentY': max(values),
            'blank': max(0, lower - min(values), max(values) - upper),
            'scrollbarStable': scrollbar_stable}


@pytest.mark.parametrize('browser', ['chrome', 'edge', 'firefox'])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_install_guide_continuous_native_wheel_has_zero_boundary_blank(
        quick_window, qapp, tmp_path, browser, theme):
    window = quick_window
    window.theme.set_mode(theme)
    dialog, scroll, flickable, background = open_guide(window, qapp, tmp_path, browser)
    bar = vertical_bar(scroll)
    before = geometry(dialog)
    background_before = (background.property('contentY'), background.property('contentHeight'))
    measurements = [edge_measurements(window, qapp, flickable, edge, pixels=pixels, bar=bar)
                    for pixels in (0, 48) for edge in ('top', 'bottom')]
    print('GUIDE BOUNDARY MEASUREMENTS = ' + json.dumps({
        'flickableClass': flickable.metaObject().className(),
        'boundsBehavior': qml_number(window, flickable, 'boundsBehavior'),
        'contentHeight': flickable.property('contentHeight'),
        'viewportHeight': flickable.height(), 'measurements': measurements,
    }, default=str))
    assert geometry(dialog) == before
    assert (background.property('contentY'), background.property('contentHeight')) == background_before
    assert qml_number(window, flickable, 'boundsBehavior') == 0
    assert all(item['blank'] <= .01 for item in measurements), measurements
    assert all(item['scrollbarStable'] for item in measurements), measurements
    QTest.keyClick(window.root, Qt.Key_Escape)
    run_frames(qapp, 240)
    entry = find_item(window, 'browser-install-guide')
    click_item(window, entry)
    run_frames(qapp, 250)
    _, _, reopened = guide_viewport(window)
    assert bounds(reopened)[0] - .01 <= reopened.property('contentY') <= bounds(reopened)[1] + .01
    assert not window.qml_warnings


def test_install_guide_language_height_changes_keep_content_within_bounds(
        quick_window, qapp, tmp_path):
    window = quick_window
    dialog, scroll, flickable, _ = open_guide(window, qapp, tmp_path)
    measurements = []
    for locale in ('ru-RU', *SUPPORTED_LOCALES):
        flickable.setProperty('contentY', bounds(flickable)[1])
        run_frames(qapp, 240)
        frame_values = []
        def frame():
            lower, upper = bounds(flickable)
            value = flickable.property('contentY')
            frame_values.append((value, lower, upper,
                                 flickable.property('contentHeight'), flickable.height()))
        window.root.frameSwapped.connect(frame)
        window.i18n.setLanguage(locale)
        run_frames(qapp, 240)
        window.root.frameSwapped.disconnect(frame)
        frame()
        measurements.append({'locale': locale, 'frames': frame_values})
    print('GUIDE LANGUAGE BOUNDS = ' + json.dumps(measurements))
    assert all(lower - .01 <= value <= upper + .01
               for measurement in measurements
               for value, lower, upper, _, _ in measurement['frames']), measurements
    assert not window.qml_warnings


@pytest.mark.parametrize('edge', ['top', 'bottom'])
def test_install_guide_touch_scroll_has_no_physical_overshoot(
        quick_window, qapp, tmp_path, edge):
    window = quick_window
    _, _, flickable, _ = open_guide(window, qapp, tmp_path)
    flickable.setProperty('contentY', bounds(flickable)[0 if edge == 'top' else 1])
    run_frames(qapp, 120)
    start = flickable.mapToScene(QPointF(flickable.width() / 2, flickable.height() / 2)).toPoint()
    device = QTest.createTouchDevice()
    sequence = QTest.touchEvent(window.root, device)
    sequence.press(0, start).commit()
    run_frames(qapp, 20)
    measurements = []
    direction = 1 if edge == 'top' else -1
    for distance in (30, 60, 90, 120, 150):
        sequence.move(0, start + QPoint(0, direction * distance)).commit()
        run_frames(qapp, 20)
        lower, upper = bounds(flickable)
        measurements.append((flickable.property('contentY'), lower, upper,
                             flickable.property('verticalOvershoot')))
    sequence.release(0, start + QPoint(0, direction * 150)).commit()
    run_frames(qapp, 240)
    print('GUIDE TOUCH OVERSHOOT = ' + json.dumps(measurements))
    assert all(lower - .01 <= value <= upper + .01 for value, lower, upper, _ in measurements), measurements
    assert not window.qml_warnings


def test_ordinary_dialog_retains_native_scroll_configuration(quick_window, qapp):
    window = quick_window
    window.dialogs.info('Information', 'Message')
    run_frames(qapp, 250)
    dialog = find_item(window, 'dialog-info')
    scroll = dialog.property('contentItem')
    flickable = scroll.property('contentItem')
    assert qml_number(window, flickable, 'boundsBehavior') == 3
    assert dialog.property('width') == 620
    assert not find_item(window, 'browserGuideLoader').isVisible()
    assert not window.qml_warnings

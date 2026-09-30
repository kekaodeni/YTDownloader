"""Duration-aware timecodes, exercised through the real masked Qt controls."""
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt, QMetaObject, QPointF, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from conftest import find_item, run_frames
from scripts.verify_quick_ui import sample_video


def open_clip(window, qapp, duration):
    page = window.download_page
    page.show_video(replace(sample_video(), duration=duration))
    page.setAdvancedToggle('advancedExpanded', True)
    page.setAdvancedToggle('clipEnabled', True)
    run_frames(qapp)
    return page, find_item(window, 'clipStart'), find_item(window, 'clipEnd')


@pytest.mark.parametrize('duration,start,end,mask', [
    (577, '00:00', '09:37', '99:99;_'),
    (4815, '00:00:00', '01:20:15', '99:99:99;_'),
    (None, '00:00:00', '', '99:99:99;_'),
])
def test_duration_selects_time_mask_and_initial_range(quick_window, qapp, duration, start, end, mask):
    page, first, last = open_clip(quick_window, qapp, duration)
    assert first.property('inputMask') == mask
    assert last.property('inputMask') == mask
    assert page.state['clipStart'] == start
    assert page.state['clipEnd'] == end
    assert page.state['clipValid'] is (duration is not None)


@pytest.mark.parametrize('duration,typed,expected', [
    (577, '0315', '03:15'), (577, '03:15', '03:15'),
    (4815, '010530', '01:05:30'), (4815, '01:05:30', '01:05:30'),
])
@pytest.mark.parametrize('paste', [False, True])
def test_digits_and_paste_keep_fixed_separators(quick_window, qapp, duration, typed, expected, paste):
    page, first, _ = open_clip(quick_window, qapp, duration)
    first.forceActiveFocus()
    QMetaObject.invokeMethod(first, 'selectAll')
    if paste:
        QGuiApplication.clipboard().setText(typed)
        QTest.keyClick(quick_window.root, Qt.Key_V, Qt.ControlModifier)
    else:
        for character in typed:
            QTest.keyClick(quick_window.root, Qt.Key(ord(character)))
    assert first.property('text') == expected
    assert page.state['clipStart'] == expected


def test_late_duration_converts_existing_time_without_losing_values(quick_window, qapp):
    page, first, last = open_clip(quick_window, qapp, None)
    page.setAdvancedField('clipStart', '00:03:15')
    page.setAdvancedField('clipEnd', '00:05:40')
    page.show_video(replace(page.video, duration=577))
    run_frames(qapp)
    assert first.property('inputMask') == '99:99;_'
    assert first.property('text') == '03:15'
    assert last.property('text') == '05:40'
    assert page.state['clipValid']


@pytest.mark.parametrize('duration,start,end', [
    (577, '00:69', '05:40'), (4815, '01:60:99', '01:10:00'),
    (577, '05:40', '03:15'), (577, '03:15', '10:00'),
])
def test_invalid_ranges_keep_download_disabled(quick_window, qapp, duration, start, end):
    page, _, _ = open_clip(quick_window, qapp, duration)
    page.setAdvancedField('clipStart', start)
    page.setAdvancedField('clipEnd', end)
    assert not page.state['clipValid']
    assert not find_item(quick_window, 'downloadButton').isEnabled()


def test_delete_backspace_and_arrow_keys_do_not_edit_colons(quick_window, qapp):
    page, first, _ = open_clip(quick_window, qapp, 577)
    page.setAdvancedField('clipStart', '03:15')
    first.forceActiveFocus()
    first.setProperty('cursorPosition', 3)
    QTest.keyClick(quick_window.root, Qt.Key_Backspace)
    assert first.property('displayText')[2] == ':'
    assert not page.state['clipValid']
    QTest.keyClick(quick_window.root, Qt.Key_2)
    assert first.property('text') == '02:15'
    first.setProperty('cursorPosition', 1)
    QTest.keyClick(quick_window.root, Qt.Key_Right)
    assert first.property('cursorPosition') >= 3
    QTest.keyClick(quick_window.root, Qt.Key_Left)
    assert first.property('cursorPosition') <= 1
    first.setProperty('cursorPosition', 2)
    QTest.keyClick(quick_window.root, Qt.Key_Delete)
    assert first.property('displayText')[2] == ':'


def test_only_ascii_digits_can_be_entered_or_pasted(quick_window, qapp):
    page, first, _ = open_clip(quick_window, qapp, 577)
    first.forceActiveFocus()
    QMetaObject.invokeMethod(first, 'selectAll')
    QGuiApplication.clipboard().setText('٠٣:١٥')
    QTest.keyClick(quick_window.root, Qt.Key_V, Qt.ControlModifier)
    assert page.state['clipStart'] == '00:00'
    assert first.property('text') == '00:00'
    QGuiApplication.sendEvent(quick_window.root, QKeyEvent(QEvent.KeyPress, Qt.Key_unknown, Qt.NoModifier, '３'))
    assert page.state['clipStart'] == '00:00'


def test_click_near_colon_places_cursor_on_a_digit_slot(quick_window, qapp):
    page, first, _ = open_clip(quick_window, qapp, 577)
    # Reveal the editor and click the actual separator position.
    from test_download_view_scroll import scroll_to
    scroll_to(quick_window, first)
    run_frames(qapp, 100)
    from PySide6.QtCore import Q_ARG, Q_RETURN_ARG
    rectangle = QMetaObject.invokeMethod(first, 'positionToRectangle', Q_RETURN_ARG('QRectF'), Q_ARG(int, 2))
    point = first.mapToScene(QPointF(rectangle.x() + 2, first.height() / 2)).toPoint()
    QTest.mouseClick(quick_window.root, Qt.LeftButton, Qt.NoModifier, point)
    assert first.property('cursorPosition') != 2


def test_new_media_gets_fresh_duration_defaults(quick_window, qapp):
    page, first, last = open_clip(quick_window, qapp, 577)
    page.setAdvancedField('clipStart', '03:15')
    page.show_video(replace(page.video, video_id='new', duration=4815))
    run_frames(qapp)
    assert first.property('text') == '00:00:00'
    assert last.property('text') == '01:20:15'


def test_late_short_duration_does_not_truncate_an_hour_of_user_input(quick_window, qapp):
    page, first, _ = open_clip(quick_window, qapp, None)
    page.setAdvancedField('clipStart', '01:03:15')
    page.setAdvancedField('clipEnd', '01:05:40')
    page.show_video(replace(page.video, duration=577))
    run_frames(qapp)
    assert first.property('text') == '01:03:15'
    assert first.property('inputMask') == '99:99:99;_'
    assert not page.state['clipValid']

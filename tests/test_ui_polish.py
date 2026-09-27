from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from conftest import click_item, find_item, run_frames
from test_history_repository import _record
from yt_downloader.core.models import CookieProfile, TaskStatus
from test_download_service import _request


def _object_names(window):
    pending = [window.root.contentItem()]
    while pending:
        item = pending.pop()
        yield item.objectName()
        pending.extend(item.childItems())


def test_history_management_toolbar_has_one_tri_state_select_all(quick_window, qapp, tmp_path):
    page = quick_window.history_page
    page.set_records([_record(tmp_path, key, TaskStatus.COMPLETED) for key in ('one', 'two', 'three')])
    quick_window._select_page(1)
    page.manage(True)
    run_frames(qapp)

    action_names = ('historySelectAll', 'historyDeleteSelected', 'historyClear', 'historyManageToggle')
    actions = [find_item(quick_window, name) for name in action_names]
    assert all(action.isVisible() for action in actions)
    centers = [action.y() + action.height() / 2 for action in actions]
    assert max(centers) - min(centers) < 1
    assert 'historySelectNone' not in set(_object_names(quick_window))

    check = find_item(quick_window, 'historySelectAll')
    assert check.property('text') == '全选'
    assert check.property('checkState').value == 0
    assert check.property('enabled')  # Non-empty history is selectable.

    page.toggle('one')
    run_frames(qapp)
    assert check.property('checkState').value == 1
    assert page.state['checkedCount'] == 1
    assert page.state['managementText'] == '已选择 1 项'

    page.selectAll(True)
    run_frames(qapp)
    assert check.property('checkState').value == 2
    assert page.state['checkedCount'] == 3

    page.toggle('two')
    run_frames(qapp)
    assert check.property('checkState').value == 1

    # Clicking the indicator or the label while partial selects all.
    point = check.mapToScene(QPointF(17, check.height() / 2)).toPoint()
    QTest.mouseClick(quick_window.root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    run_frames(qapp)
    assert page.state['checkedCount'] == 3
    assert check.property('checkState').value == 2

    # The label is part of the same control hit target.
    click_item(quick_window, check)
    run_frames(qapp)
    assert page.state['checkedCount'] == 0
    assert check.property('checkState').value == 0
    click_item(quick_window, check)
    run_frames(qapp)
    assert page.state['checkedCount'] == 3
    assert check.property('checkState').value == 2
    click_item(quick_window, check)
    run_frames(qapp)
    assert page.state['checkedCount'] == 0
    assert check.property('checkState').value == 0

    indicator = find_item(quick_window, 'historyCheckboxIndicator-one')
    row_check = find_item(quick_window, 'historySelect-one')
    assert row_check.isVisible()
    assert indicator.width() <= 18 and indicator.height() <= 18

    page.set_records([])
    run_frames(qapp)
    assert check.property('checkState').value == 0
    assert not check.property('enabled')


def test_history_row_and_checkbox_selection_keep_select_all_in_sync(quick_window, qapp, tmp_path):
    page = quick_window.history_page
    page.set_records([_record(tmp_path, key, TaskStatus.COMPLETED) for key in ('one', 'two')])
    quick_window._select_page(1)
    page.manage(True)
    run_frames(qapp)
    top_check = find_item(quick_window, 'historySelectAll')
    click_item(quick_window, find_item(quick_window, 'historyTitle-one'))
    run_frames(qapp)
    assert page.state['checkedCount'] == 1
    assert top_check.property('checkState').value == 1
    row_check = find_item(quick_window, 'historySelect-two')
    click_item(quick_window, row_check)
    run_frames(qapp)
    assert page.state['checkedCount'] == 2
    assert top_check.property('checkState').value == 2
    assert page.model.get(1)['checked'] is True

    page.selectAll(True)
    page.set_records([_record(tmp_path, 'two', TaskStatus.COMPLETED)])
    run_frames(qapp)
    assert page.state['checkedCount'] == 1
    assert top_check.property('checkState').value == 2

    page.set_records([])
    run_frames(qapp)
    assert top_check.property('checkState').value == 0


def test_cookie_help_and_saved_profile_actions_have_button_treatment(quick_window, qapp):
    quick_window._select_page(2)
    quick_window.cookies.set_profiles((CookieProfile('fixture', 'Fixture', 'browser',
                                                     browser='firefox', domain_hint='example.org'),))
    run_frames(qapp)

    help_button = find_item(quick_window, 'cookiePrivacyHelp')
    edit_button = find_item(quick_window, 'cookieEdit-fixture')
    delete_button = find_item(quick_window, 'cookieDelete-fixture')
    assert help_button.property('text') == '查看 Cookie 用途与隐私说明'
    assert help_button.property('appearance') == 'normal'
    assert delete_button.property('appearance') == 'danger'
    assert abs(edit_button.height() - delete_button.height()) < 1


def test_download_cookie_button_and_aligned_media_fields(quick_window, qapp, tmp_path):
    page = quick_window.download_page
    page.show_video(_request(tmp_path).video)
    run_frames(qapp)

    names = set(_object_names(quick_window))
    assert 'nativeFormatSwitch' not in names
    cookie_button = find_item(quick_window, 'cookieManagementButton')
    format_hint = find_item(quick_window, 'formatSelectionHint')
    combo = find_item(quick_window, 'formatCombo')
    assert cookie_button.property('appearance') == 'normal'
    assert combo.isEnabled()
    assert 'yt-dlp' in format_hint.property('text')
    assert page.state['qualityAuto'] is True

    filename = find_item(quick_window, 'filenameInput')
    directory = find_item(quick_window, 'directoryInput')
    origin = quick_window.root.contentItem()
    filename_x = filename.mapToItem(origin, QPointF(0, 0)).x()
    directory_x = directory.mapToItem(origin, QPointF(0, 0)).x()
    assert abs(filename_x - directory_x) < 1
    assert filename.height() <= 42 and directory.height() <= 42

    page.selectFormat(0)
    assert page.state['qualityAuto'] is False

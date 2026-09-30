from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtGui import QAccessible, QColor
from PySide6.QtTest import QTest
import pytest

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
    delete = find_item(quick_window, 'historyDeleteSelected')
    assert not delete.property('enabled')

    page.toggle('one')
    run_frames(qapp)
    assert check.property('checkState').value == 1
    assert page.state['checkedCount'] == 1
    assert page.state['managementText'] == '已选择 1 项'
    assert delete.property('enabled')

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


def test_history_management_toolbar_groups_selection_and_hides_item_actions(quick_window, qapp, tmp_path):
    page = quick_window.history_page
    page.set_records([_record(tmp_path, key, TaskStatus.COMPLETED) for key in ('one', 'two', 'three')])
    quick_window._select_page(1)
    run_frames(qapp)
    item_actions = ('historyItemOpen', 'historyItemFolder', 'historyItemCopy',
                    'historyItemCover', 'historyItemRetry')
    assert all(find_item(quick_window, name).isVisible() for name in item_actions)
    assert not find_item(quick_window, 'historyManagementToolbar').isVisible()

    page.manage(True)
    run_frames(qapp)
    toolbar = find_item(quick_window, 'historyManagementToolbar')
    selection_group = find_item(quick_window, 'historySelectionGroup')
    action_group = find_item(quick_window, 'historyActionGroup')
    select_all = find_item(quick_window, 'historySelectAll')
    selected_count = find_item(quick_window, 'historySelectedCount')
    delete = find_item(quick_window, 'historyDeleteSelected')
    clear = find_item(quick_window, 'historyClear')
    done = find_item(quick_window, 'historyManageToggle')
    assert toolbar.isVisible()
    assert selection_group.x() < action_group.x()
    assert abs(selection_group.x()) < 1
    assert abs(action_group.x() + action_group.width() - toolbar.width()) < 1
    assert selected_count.property('text') == '已选择 0 项'
    assert abs(selected_count.y() + selected_count.height() / 2 - select_all.y() - select_all.height() / 2) < 1
    assert not delete.property('enabled')
    assert all(not find_item(quick_window, name).isVisible() for name in item_actions)
    assert all(button.isVisible() for button in (select_all, delete, clear, done))
    assert max(button.y() + button.height() / 2 for button in (select_all, delete, clear, done)) - min(
        button.y() + button.height() / 2 for button in (select_all, delete, clear, done)) < 1

    page.toggle('one')
    run_frames(qapp)
    assert selected_count.property('text') == '已选择 1 项'
    assert delete.property('enabled')

    page.selectAll(True)
    run_frames(qapp)
    assert selected_count.property('text') == '已选择 3 项'
    assert select_all.property('checkState').value == 2

    page.manage(False)
    run_frames(qapp)
    assert not toolbar.isVisible()
    assert all(find_item(quick_window, name).isVisible() for name in item_actions)


def test_history_management_toolbar_wraps_without_overlapping_at_narrow_width(quick_window, qapp, tmp_path):
    page = quick_window.history_page
    page.set_records([_record(tmp_path, key, TaskStatus.COMPLETED) for key in ('one', 'two', 'three')])
    quick_window._select_page(1)
    page.manage(True)
    quick_window.root.resize(620, 760)
    run_frames(qapp)

    toolbar = find_item(quick_window, 'historyManagementToolbar')
    selection_group = find_item(quick_window, 'historySelectionGroup')
    action_group = find_item(quick_window, 'historyActionGroup')
    left = selection_group.mapToItem(toolbar, QPointF(0, 0))
    right = action_group.mapToItem(toolbar, QPointF(0, 0))
    assert left.x() + selection_group.width() <= toolbar.width()
    assert right.x() + action_group.width() <= toolbar.width()
    assert right.y() >= left.y() + selection_group.height() or right.x() >= left.x() + selection_group.width()
    assert toolbar.height() >= max(left.y() + selection_group.height(), right.y() + action_group.height())


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_history_select_all_uses_project_selection_control(quick_window, qapp, tmp_path, mode):
    page = quick_window.history_page
    page.set_records([_record(tmp_path, key, TaskStatus.COMPLETED) for key in ('one', 'two', 'three')])
    quick_window._select_page(1)
    quick_window.theme.set_mode(mode)
    page.manage(True)
    run_frames(qapp)

    check = find_item(quick_window, 'historySelectAll')
    delete = find_item(quick_window, 'historyDeleteSelected')
    count = find_item(quick_window, 'historySelectedCount')
    indicator = find_item(quick_window, 'historySelectAllIndicator')
    partial_mark = find_item(quick_window, 'historySelectAllPartialMark')
    check_mark = find_item(quick_window, 'historySelectAllCheckMark')
    row_indicator = find_item(quick_window, 'historyCheckboxIndicator-one')
    assert check.height() == delete.height() == 38
    assert check.property('tristate')
    assert check.property('appearance') is None
    assert count.property('text') == '已选择 0 项'
    assert count.x() - check.x() - check.width() == 14
    assert find_item(quick_window, 'historySelectionGroup').x() < find_item(quick_window, 'historyActionGroup').x()
    assert indicator.width() == row_indicator.width() == 18
    assert indicator.property('radius') == row_indicator.property('radius') == 5
    assert not partial_mark.property('visible') and not check_mark.property('visible')
    assert indicator.property('color').name().lower() == quick_window.theme.state['surface'].lower()

    point = check.mapToScene(QPointF(indicator.x() + indicator.width() / 2, check.height() / 2)).toPoint()
    QTest.mouseMove(quick_window.root, QPointF(0, 0).toPoint())
    run_frames(qapp, 60)
    QTest.mouseMove(quick_window.root, point)
    run_frames(qapp, 180)
    assert indicator.property('color').name().lower() == quick_window.theme.state['subtle'].lower()

    page.toggle('one')
    run_frames(qapp)
    assert check.property('checkState').value == 1
    assert count.property('text') == '已选择 1 项'
    assert partial_mark.property('visible') and not check_mark.property('visible')
    assert indicator.property('color').name().lower() == quick_window.theme.state['accent'].lower()
    assert partial_mark.property('color').name().lower() == quick_window.theme.state['onAccent'].lower()

    page.selectAll(True)
    run_frames(qapp)
    assert check.property('checkState').value == 2
    assert count.property('text') == '已选择 3 项'
    assert check_mark.property('visible') and not partial_mark.property('visible')
    assert indicator.property('color').name().lower() == quick_window.theme.state['accent'].lower()
    assert check_mark.property('color').name().lower() == quick_window.theme.state['onAccent'].lower()

    find_item(quick_window, 'historyList').forceActiveFocus()
    for _ in range(20):
        QTest.keyClick(quick_window.root, Qt.Key_Tab)
        run_frames(qapp, 20)
        if check.property('activeFocus'):
            break
    assert check.property('activeFocus')
    assert check.property('visualFocus')

    page.set_records([])
    run_frames(qapp)
    assert not check.property('enabled')
    assert check.property('checkState').value == 0
    assert indicator.property('color').name().lower() == quick_window.theme.state['subtle'].lower()


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


def test_history_select_all_keyboard_and_accessible_state(quick_window, qapp, tmp_path):
    page = quick_window.history_page
    page.set_records([_record(tmp_path, key, TaskStatus.COMPLETED) for key in ('one', 'two')])
    quick_window._select_page(1)
    page.manage(True)
    run_frames(qapp)
    select_all = find_item(quick_window, 'historySelectAll')

    find_item(quick_window, 'historyList').forceActiveFocus()
    for _ in range(20):
        QTest.keyClick(quick_window.root, Qt.Key_Tab)
        run_frames(qapp, 20)
        if select_all.property('activeFocus'):
            break
    assert select_all.property('activeFocus')
    accessible = QAccessible.queryAccessibleInterface(select_all)
    count_accessible = QAccessible.queryAccessibleInterface(find_item(quick_window, 'historySelectedCount'))
    assert accessible.text(QAccessible.Text.Name) == '全选'
    assert accessible.text(QAccessible.Text.Description) == '未选中'
    assert count_accessible.text(QAccessible.Text.Name) == '已选择 0 项'

    page.toggle('one')
    run_frames(qapp)
    assert accessible.text(QAccessible.Text.Description) == '部分选中'
    assert count_accessible.text(QAccessible.Text.Name) == '已选择 1 项'

    QTest.keyClick(quick_window.root, Qt.Key_Space)
    run_frames(qapp)
    assert page.state['checkedCount'] == 2
    assert select_all.property('checkState').value == 2
    assert accessible.text(QAccessible.Text.Description) == '已全选'
    assert count_accessible.text(QAccessible.Text.Name) == '已选择 2 项'

    QTest.keyClick(quick_window.root, Qt.Key_Return)
    run_frames(qapp)
    assert page.state['checkedCount'] == 0
    assert select_all.property('checkState').value == 0
    assert accessible.text(QAccessible.Text.Description) == '未选中'

    QTest.keyClick(quick_window.root, Qt.Key_Enter)
    run_frames(qapp)
    assert page.state['checkedCount'] == 2
    assert select_all.property('checkState').value == 2


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


def test_settings_profiles_follow_v2_information_architecture(quick_window, qapp):
    quick_window._select_page(2)
    quick_window.settings_page.selectCategory(1)
    run_frames(qapp)
    default_combo = find_item(quick_window, 'defaultDownloadProfile')
    empty_state = find_item(quick_window, 'emptyDownloadProfiles')
    create_button = find_item(quick_window, 'newDownloadProfile')
    assert default_combo.property('count') == 2
    assert default_combo.property('currentIndex') == 0
    assert empty_state.isVisible()
    assert not quick_window.root.findChild(QObject, 'builtinProfile-auto')
    assert not quick_window.root.findChild(QObject, 'builtinProfile-best')

    quick_window.settings_page.newProfile()
    run_frames(qapp)
    editor = find_item(quick_window, 'downloadProfileEditor')
    assert editor.property('visible')
    assert find_item(quick_window, 'profileQuality').isVisible()
    assert find_item(quick_window, 'profileCodec').isVisible()
    quick_window.settings_page.editProfileField('name', '2160p 下载')
    quick_window.settings_page.editProfileField('quality_tier', '2160p')
    quick_window.settings_page.saveProfile()
    run_frames(qapp)

    settings = quick_window.settings_page
    profile = settings.current_settings().custom_download_profiles[0]
    assert default_combo.property('count') == 3
    assert default_combo.property('currentIndex') == 0
    row = find_item(quick_window, 'customProfile-' + profile.id)
    assert row.isVisible()
    assert not empty_state.isVisible()
    assert find_item(quick_window, 'editProfile-' + profile.id).isVisible()
    assert find_item(quick_window, 'deleteProfile-' + profile.id).isVisible()
    assert not quick_window.root.findChild(QObject, 'copyProfile-' + profile.id)
    assert not quick_window.root.findChild(QObject, 'setDefaultProfile-' + profile.id)
    assert create_button.isVisible()
    assert not quick_window.root.findChild(QObject, 'downloadProfileSelector')
    assert not quick_window.root.findChild(QObject, 'profileManagerButton')

    settings.setDefaultProfile(profile.id)
    run_frames(qapp)
    assert default_combo.property('currentIndex') == 2


@pytest.mark.parametrize('mode,surface', [('light', '#FFFFFF'), ('dark', '#2A2F39')])
def test_profile_editor_dialog_uses_one_rounded_surface_for_all_corners(quick_window, qapp, mode, surface):
    quick_window.theme.set_mode(mode)
    quick_window._select_page(2)
    quick_window.settings_page.newProfile()
    run_frames(qapp)

    editor = find_item(quick_window, 'downloadProfileEditor')
    image = quick_window.root.grabWindow()
    dpr = image.devicePixelRatio()
    left = round(editor.property('x') * dpr)
    top = round(editor.property('y') * dpr)
    right = round((editor.property('x') + editor.property('width')) * dpr) - 1
    bottom = round((editor.property('y') + editor.property('height')) * dpr) - 1
    inset = round(2 * dpr)
    corners = (
        image.pixelColor(left + inset, top + inset),
        image.pixelColor(right - inset, top + inset),
        image.pixelColor(left + inset, bottom - inset),
        image.pixelColor(right - inset, bottom - inset),
    )

    assert all(color != QColor(surface) for color in corners)
    assert editor.property('title') == ''


def test_profile_editor_footer_stays_inside_rounded_safe_area(quick_window, qapp):
    quick_window._select_page(2)
    quick_window.settings_page.newProfile()
    run_frames(qapp)

    editor = find_item(quick_window, 'downloadProfileEditor')
    cancel = find_item(quick_window, 'profileEditorCancel')
    save = find_item(quick_window, 'saveProfile')
    root_item = quick_window.root.contentItem()
    cancel_origin = cancel.mapToItem(root_item, QPointF(0, 0))
    save_origin = save.mapToItem(root_item, QPointF(0, 0))
    editor_right = editor.property('x') + editor.property('width')
    editor_bottom = editor.property('y') + editor.property('height')

    assert editor_right - (save_origin.x() + save.width()) >= 24
    assert editor_bottom - (save_origin.y() + save.height()) >= 24
    assert abs(cancel.height() - save.height()) < 1
    assert abs(cancel_origin.y() - save_origin.y()) < 1
    assert save_origin.x() - (cancel_origin.x() + cancel.width()) >= 8


def test_profile_editor_subtitle_fields_keep_dependent_disabled_state(quick_window, qapp):
    quick_window._select_page(2)
    quick_window.settings_page.newProfile()
    run_frames(qapp)

    subtitle = find_item(quick_window, 'profileSubtitleEnabled')
    automatic = find_item(quick_window, 'profileSubtitleAuto')
    subtitle_format = find_item(quick_window, 'profileSubtitleFormat')
    embed = find_item(quick_window, 'profileSubtitleEmbed')
    assert not automatic.isEnabled()
    assert not subtitle_format.isEnabled()
    assert not embed.isEnabled()

    quick_window.settings_page.editProfileField('subtitle_enabled', True)
    run_frames(qapp)
    assert subtitle.property('checked')
    assert automatic.isEnabled()
    assert subtitle_format.isEnabled()
    assert embed.isEnabled()


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

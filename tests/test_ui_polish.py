from PySide6.QtCore import QPointF

from conftest import find_item, run_frames
from test_history_repository import _record
from yt_downloader.core.models import CookieProfile, TaskStatus
from test_download_service import _request


def _object_names(window):
    pending = [window.root.contentItem()]
    while pending:
        item = pending.pop()
        yield item.objectName()
        pending.extend(item.childItems())


def test_history_management_toolbar_and_compact_checkboxes(quick_window, qapp, tmp_path):
    page = quick_window.history_page
    page.set_records([_record(tmp_path, 'done', TaskStatus.COMPLETED)])
    quick_window._select_page(1)
    page.manage(True)
    run_frames(qapp)

    action_names = ('historySelectAll', 'historySelectNone', 'historyDeleteSelected',
                    'historyClear', 'historyManageToggle')
    actions = [find_item(quick_window, name) for name in action_names]
    assert all(action.isVisible() for action in actions)
    centers = [action.y() + action.height() / 2 for action in actions]
    assert max(centers) - min(centers) < 1

    check = find_item(quick_window, 'historySelect-done')
    indicator = find_item(quick_window, 'historyCheckboxIndicator-done')
    assert check.isVisible()
    assert indicator.width() <= 18 and indicator.height() <= 18
    assert abs(indicator.y() + indicator.height() / 2 - check.height() / 2) < 1


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

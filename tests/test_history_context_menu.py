from dataclasses import replace
from PySide6.QtCore import Qt, QPointF, QObject
from PySide6.QtTest import QTest
import pytest
from yt_downloader.core.models import TaskStatus
from test_history_repository import _record
from conftest import find_item, run_frames, click_item

def prepare(window, tmp_path, qapp):
    page = window.history_page
    page.set_records([_record(tmp_path, 'first', TaskStatus.COMPLETED), _record(tmp_path,'second',TaskStatus.FAILED)])
    window._select_page(1)
    run_frames(qapp)
    return page


def click_center(window, item, qapp):
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(window.root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    run_frames(qapp, 80)


@pytest.mark.parametrize('mode', ['light','dark'])
@pytest.mark.parametrize('target_name', [
    'historyTitle-first', 'historyCover-first', 'historyStatus-first',
])
def test_management_clicking_row_content_toggles_shared_selection(quick_window,tmp_path,qapp,target_name,mode):
    page = prepare(quick_window,tmp_path,qapp)
    quick_window.theme.set_mode(mode)
    page.manage(True)
    target = find_item(quick_window,target_name)

    click_center(quick_window,target,qapp)
    assert page.state['checkedCount'] == 1
    assert page.model.get(0)['checked'] is True

    click_center(quick_window,target,qapp)
    assert page.state['checkedCount'] == 0
    assert page.model.get(0)['checked'] is False


@pytest.mark.parametrize('mode', ['light','dark'])
def test_management_row_hover_shows_select_cursor_and_preserves_selected_background(quick_window,tmp_path,qapp,mode):
    page = prepare(quick_window,tmp_path,qapp)
    quick_window.theme.set_mode(mode)
    page.manage(True)
    row = find_item(quick_window,'history-first')
    point = row.mapToScene(QPointF(row.width() - 4, row.height() / 2)).toPoint()

    QTest.mouseMove(quick_window.root,QPointF(0,0).toPoint())
    run_frames(qapp,60)
    QTest.mouseMove(quick_window.root,point)
    run_frames(qapp,60)
    assert row.property('rowCursorShape') == Qt.PointingHandCursor.value
    assert row.property('color').name().lower() == quick_window.theme.state['subtle'].lower()

    QTest.mouseClick(quick_window.root,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
    run_frames(qapp,60)
    assert page.state['checkedCount'] == 1
    assert row.property('color').name().lower() == quick_window.theme.state['selection'].lower()


def test_management_clicking_row_padding_toggles_but_normal_mode_does_not(quick_window,tmp_path,qapp):
    page = prepare(quick_window,tmp_path,qapp)
    row = find_item(quick_window,'history-first')
    point = row.mapToScene(QPointF(row.width() - 3, row.height() - 3)).toPoint()

    QTest.mouseClick(quick_window.root,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
    run_frames(qapp,80)
    assert page.state['checkedCount'] == 0
    assert page.selected_record().task_id == 'first'

    page.manage(True)
    QTest.mouseClick(quick_window.root,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
    run_frames(qapp,80)
    assert page.state['checkedCount'] == 1


def test_management_checkbox_click_toggles_once_and_syncs_batch_controls(quick_window,tmp_path,qapp):
    page = prepare(quick_window,tmp_path,qapp)
    page.manage(True)
    checkbox = find_item(quick_window,'historySelect-first')
    delete = find_item(quick_window,'historyDeleteSelected')

    click_center(quick_window,checkbox,qapp)
    assert page.state['checkedCount'] == 1
    assert page.model.get(0)['checked'] is True
    assert delete.property('enabled') is True

    page.selectAll(True)
    assert page.state['checkedCount'] == 2
    click_center(quick_window,find_item(quick_window,'historyTitle-first'),qapp)
    assert page.state['checkedCount'] == 1
    assert page.model.get(0)['checked'] is False
    assert page.model.get(1)['checked'] is True
    assert '已选择 1 项' == page.state['managementText']

    click_center(quick_window,checkbox,qapp)
    assert page.state['checkedCount'] == 2

    click_center(quick_window,find_item(quick_window,'historySelectAll'),qapp)
    assert page.state['checkedCount'] == 0
    assert delete.property('enabled') is False
    assert page.state['managementText'] == '已选择 0 项'

def test_context_menu_selects_pointer_record_and_has_all_actions(quick_window,tmp_path,qapp):
    page = prepare(quick_window,tmp_path,qapp)
    row = find_item(quick_window,'history-second')
    click_item(quick_window,row,Qt.RightButton)
    run_frames(qapp)
    assert page.selected_record().task_id == 'second'
    menu = find_item(quick_window,'historyMenu')
    assert menu.property('visible')
    assert menu.property('count') == 7


def test_management_context_delete_on_selected_row_deletes_complete_selection(quick_window,tmp_path,qapp,qtbot):
    page = prepare(quick_window,tmp_path,qapp)
    page.set_records([
        _record(tmp_path,'first',TaskStatus.COMPLETED),
        _record(tmp_path,'second',TaskStatus.FAILED),
        _record(tmp_path,'third',TaskStatus.COMPLETED),
    ])
    run_frames(qapp)
    page.manage(True)
    page.toggle('first'); page.toggle('second')

    click_item(quick_window,find_item(quick_window,'history-first'),Qt.RightButton)
    run_frames(qapp)
    assert page.state['checkedCount'] == 2
    assert page.model.get(0)['checked'] and page.model.get(1)['checked']
    assert find_item(quick_window,'historyContextDelete').property('text') == '删除所选'
    before = len(quick_window.dialogs.sessions)
    deleted = []
    page.delete_many_requested.connect(deleted.append)
    page.action('delete')
    assert len(quick_window.dialogs.sessions) == before + 1
    quick_window.dialogs.sessions[-1].answer(True)
    assert deleted == [('first','second')]


def test_management_context_click_on_unselected_row_makes_it_the_only_delete_target(quick_window,tmp_path,qapp):
    page = prepare(quick_window,tmp_path,qapp)
    page.set_records([
        _record(tmp_path,'first',TaskStatus.COMPLETED),
        _record(tmp_path,'second',TaskStatus.FAILED),
        _record(tmp_path,'third',TaskStatus.COMPLETED),
    ])
    run_frames(qapp)
    page.manage(True)
    page.toggle('first'); page.toggle('second')

    click_item(quick_window,find_item(quick_window,'history-third'),Qt.RightButton)
    run_frames(qapp)
    assert page.state['selectedId'] == 'third'
    assert page.state['checkedCount'] == 1
    assert [row['id'] for row in page.model.rows if row['checked']] == ['third']
    assert find_item(quick_window,'historyContextDelete').property('text') == '删除记录'
    deleted = []
    page.delete_many_requested.connect(deleted.append)
    page.action('delete')
    quick_window.dialogs.sessions[-1].answer(True)
    assert deleted == [('third',)]


def test_single_item_context_action_targets_pointer_record_with_multiple_selected(quick_window,tmp_path,qapp):
    page = prepare(quick_window,tmp_path,qapp)
    first = replace(_record(tmp_path,'first',TaskStatus.COMPLETED),url='https://example.test/first')
    second = replace(_record(tmp_path,'second',TaskStatus.FAILED),url='https://example.test/second')
    page.set_records([first,second]); run_frames(qapp)
    page.manage(True); page.toggle('first'); page.toggle('second')

    click_item(quick_window,find_item(quick_window,'history-first'),Qt.RightButton)
    run_frames(qapp)
    copied = []
    page.copy_link_requested.connect(copied.append)
    page.action('copy')
    assert copied == ['https://example.test/first']
    assert page.state['checkedCount'] == 2

def test_delete_requires_confirmation_and_is_disabled_for_active_task(quick_window,tmp_path,qtbot):
    page = quick_window.history_page; deleted = []
    page.delete_requested.connect(deleted.append)
    page.set_records([_record(tmp_path,'done',TaskStatus.COMPLETED),_record(tmp_path,'active',TaskStatus.DOWNLOADING_VIDEO)])
    page.select('active'); page.action('delete')
    assert not quick_window.dialogs.sessions
    page.select('done'); page.action('delete')
    assert not deleted
    quick_window.dialogs.sessions[-1].answer(False)
    assert not deleted
    page.action('delete')
    quick_window.dialogs.sessions[-1].answer(True)
    assert [r.task_id for r in deleted] == ['done']

def test_shift_f10_opens_context_menu_for_keyboard_selection(quick_window,tmp_path,qapp):
    page = prepare(quick_window,tmp_path,qapp)
    page.select('first'); find_item(quick_window,'historyList').forceActiveFocus()
    QTest.keyClick(quick_window.root,Qt.Key_F10,Qt.ShiftModifier)
    run_frames(qapp)
    assert find_item(quick_window,'historyMenu').property('visible')

def test_management_selects_only_terminal_records(quick_window,tmp_path,qtbot):
    page = quick_window.history_page
    page.set_records([_record(tmp_path,'done',TaskStatus.COMPLETED),_record(tmp_path,'active',TaskStatus.DOWNLOADING_VIDEO),_record(tmp_path,'failed',TaskStatus.FAILED)])
    page.manage(True); page.selectAll(True)
    assert page.state['checkedCount'] == 2
    assert not page.model.get(1)['deletable']
    page.deleteChecked()
    with qtbot.waitSignal(page.delete_many_requested) as signal:
        quick_window.dialogs.sessions[-1].answer(True)
    assert signal.args == [('done','failed')]

def test_confirmed_batch_delete_exits_management_after_repository_success(quick_window,tmp_path,qapp,qtbot):
    page = quick_window.history_page
    page.set_records([_record(tmp_path,'done',TaskStatus.COMPLETED), _record(tmp_path,'failed',TaskStatus.FAILED)])
    page.manage(True); page.selectAll(True)
    with qtbot.waitSignal(page.delete_many_requested) as signal:
        page.deleteChecked()
        quick_window.dialogs.sessions[-1].answer(True)
    assert signal.args == [('done','failed')]
    assert page.state['managing'] is True
    page.batch_delete_succeeded(2, 0)
    assert page.state['managing'] is False
    assert page.state['checkedCount'] == 0
    run_frames(qapp)
    assert find_item(quick_window,'historySelectAll').property('checkState').value == 0

def test_cancelled_batch_delete_keeps_management_selection(quick_window,tmp_path,qtbot):
    page = quick_window.history_page
    page.set_records([_record(tmp_path,'done',TaskStatus.COMPLETED)])
    page.manage(True); page.selectAll(True)
    page.deleteChecked()
    quick_window.dialogs.sessions[-1].answer(False)
    assert page.state['managing'] is True
    assert page.state['checkedCount'] == 1

def test_management_keyboard_shortcuts_toggle_select_all_delete(quick_window,tmp_path,qapp,qtbot):
    page = prepare(quick_window,tmp_path,qapp)
    page.manage(True); page.select('first')
    find_item(quick_window,'historyList').forceActiveFocus()
    QTest.keyClick(quick_window.root,Qt.Key_Return)
    assert page.state['checkedCount'] == 1
    QTest.keyClick(quick_window.root,Qt.Key_Space)
    assert page.state['checkedCount'] == 0
    QTest.keyClick(quick_window.root,Qt.Key_A,Qt.ControlModifier)
    assert page.state['checkedCount'] == 2
    QTest.keyClick(quick_window.root,Qt.Key_Delete)
    with qtbot.waitSignal(page.delete_many_requested):
        quick_window.dialogs.sessions[-1].answer(True)


def test_menu_uses_shared_font_and_no_window_dimming(quick_window,tmp_path,qapp):
    page=prepare(quick_window,tmp_path,qapp)
    page.select('first');find_item(quick_window,'historyList').forceActiveFocus()
    QTest.keyClick(quick_window.root,Qt.Key_F10,Qt.ShiftModifier)
    run_frames(qapp)
    menu=find_item(quick_window,'historyMenu')
    assert menu.property('opened')
    assert not menu.property('dim')
    assert menu.property('modal')  # Outside click dismisses without activating content beneath.
    assert menu.property('font').family()=='Microsoft YaHei UI'
    assert menu.property('width')==224
    assert menu.property('height') < 280
    QTest.keyClick(quick_window.root,Qt.Key_Escape)
    run_frames(qapp)
    assert not menu.property('visible')
    assert find_item(quick_window,'historyList').hasActiveFocus()


def test_mouse_move_highlights_exactly_one_menu_item_without_dark_trails(quick_window,tmp_path,qapp):
    from PySide6.QtCore import QPointF
    page=prepare(quick_window,tmp_path,qapp)
    page.records[0].file_path.write_bytes(b'test-video')
    page.select('first');find_item(quick_window,'historyList').forceActiveFocus()
    QTest.keyClick(quick_window.root,Qt.Key_F10,Qt.ShiftModifier)
    run_frames(qapp)
    menu=find_item(quick_window,'historyMenu')
    highlights=[x for x in menu.findChildren(QObject) if x.objectName().startswith('menuHighlight-')]
    assert len(highlights)==6
    for label in ('打开文件夹','复制链接','重新下载','删除记录','复制链接'):
        target=next(x for x in highlights if x.objectName()=='menuHighlight-'+label)
        point=target.mapToScene(QPointF(target.width()/2,target.height()/2)).toPoint()
        QTest.mouseMove(quick_window.root,point)
        run_frames(qapp,20)
        assert [x.objectName() for x in highlights if x.opacity()>0] == ['menuHighlight-'+label]
        assert target.property('color').name() == quick_window.theme.state['selection'].lower()

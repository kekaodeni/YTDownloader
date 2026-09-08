from PySide6.QtCore import Qt, QPointF, QObject
from PySide6.QtTest import QTest
from yt_downloader.core.models import TaskStatus
from test_history_repository import _record
from conftest import find_item, run_frames, click_item

def prepare(window, tmp_path, qapp):
    page = window.history_page
    page.set_records([_record(tmp_path, 'first', TaskStatus.COMPLETED), _record(tmp_path,'second',TaskStatus.FAILED)])
    window._select_page(1)
    run_frames(qapp)
    return page

def test_context_menu_selects_pointer_record_and_has_all_actions(quick_window,tmp_path,qapp):
    page = prepare(quick_window,tmp_path,qapp)
    row = find_item(quick_window,'history-second')
    click_item(quick_window,row,Qt.RightButton)
    run_frames(qapp)
    assert page.selected_record().task_id == 'second'
    menu = find_item(quick_window,'historyMenu')
    assert menu.property('visible')
    assert menu.property('count') == 7

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

def test_management_keyboard_shortcuts_toggle_select_all_delete(quick_window,tmp_path,qapp,qtbot):
    page = prepare(quick_window,tmp_path,qapp)
    page.manage(True); page.select('first')
    find_item(quick_window,'historyList').forceActiveFocus()
    QTest.keyClick(quick_window.root,Qt.Key_Space)
    assert page.state['checkedCount'] == 1
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

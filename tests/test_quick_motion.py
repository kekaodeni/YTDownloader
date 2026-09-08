from dataclasses import replace
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from conftest import find_item, run_frames, click_item
from test_download_service import _request
from test_history_repository import _record
from yt_downloader.core.models import TaskStatus

def test_rapid_navigation_uses_latest_target_and_disables_outgoing(quick_window,qapp):
    field=find_item(quick_window,'urlInput')
    quick_window.download_page.set_url('retained input')
    quick_window._select_page(1)
    assert not find_item(quick_window,'pageHost-0').isEnabled()
    QTimer.singleShot(30,lambda:quick_window._select_page(3))
    QTimer.singleShot(60,lambda:quick_window._select_page(2))
    QTimer.singleShot(90,lambda:quick_window._select_page(0))
    run_frames(qapp,450)
    for i in range(4):
        host=find_item(quick_window,f'pageHost-{i}')
        assert host.opacity() == (1 if i==0 else 0)
        assert host.isEnabled() == (i==0)
    assert field.property('text') == 'retained input'

def test_navigation_mouse_and_space_immediately_change_page(quick_window,qapp):
    click_item(quick_window,find_item(quick_window,'nav-2'))
    assert quick_window.state['page']==2
    button=find_item(quick_window,'nav-1');button.forceActiveFocus()
    QTest.keyClick(quick_window.root,Qt.Key_Space)
    assert quick_window.state['page']==1

def test_reduced_motion_finishes_navigation_without_decoration(quick_window,qapp):
    quick_window.set_reduce_motion(True);quick_window._select_page(3)
    run_frames(qapp,30)
    assert find_item(quick_window,'pageHost-3').opacity()==1
    assert find_item(quick_window,'pageHost-0').opacity()==0

def test_theme_and_resize_mid_transition_keeps_latest_state(quick_window,qapp):
    quick_window._select_page(2)
    QTimer.singleShot(40,lambda:quick_window.theme.set_mode('dark'))
    QTimer.singleShot(60,lambda:quick_window.root.resize(500,560))
    run_frames(qapp,400)
    assert find_item(quick_window,'pageHost-2').opacity()==1
    assert quick_window.theme.state['dark']
    assert quick_window.root.width()==500

def test_incremental_task_changes_never_reset_the_model(quick_window,tmp_path):
    page=quick_window.download_page;resets=[]
    page.tasks.modelReset.connect(lambda:resets.append(True))
    source=_request(tmp_path)
    for i in range(40):page.add_task(replace(source,task_id=str(i)))
    for i in range(0,40,2):page.remove_task(str(i))
    assert [r['id'] for r in page.tasks.rows]==[str(i) for i in range(1,40,2)]
    assert resets==[]
    calls=[];page.remove_requested.connect(calls.append)
    page.taskAction('0','remove')
    assert calls==[]

def test_history_reuses_rows_and_preserves_selection_on_refresh(quick_window,tmp_path):
    page=quick_window.history_page;resets=[]
    page.model.modelReset.connect(lambda:resets.append(True))
    records=[_record(tmp_path,str(i),TaskStatus.COMPLETED) for i in range(300)]
    page.set_records(records);page.select('42');page.manage(True);page.toggle('42')
    page.set_records(list(reversed(records)))
    assert page.selected_record().task_id=='42'
    assert page.state['checkedCount']==1
    assert page.model.get(page.state['selectedIndex'])['id']=='42'
    assert resets==[]

def test_busy_exit_waits_for_cancel_completion(quick_window,qapp):
    cancelled=[]
    quick_window.set_download_busy(True)
    quick_window.cancel_all_requested.connect(lambda:cancelled.append(True))
    quick_window.requestClose();quick_window.requestClose()
    assert len(quick_window.dialogs.sessions)==1
    quick_window.dialogs.sessions[0].answer(True)
    assert cancelled==[True] and not quick_window.state['allowClose']
    quick_window.set_download_busy(False)
    assert quick_window.state['allowClose']

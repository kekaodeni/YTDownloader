from PySide6.QtCore import QCoreApplication, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QWheelEvent
from yt_downloader.core.models import TaskStatus
from test_history_repository import _record
from conftest import find_item, run_frames

def wheel(window, item, angle=0, pixels=0):
    local=item.mapToScene(QPointF(item.width()/2,item.height()/2))
    global_pos=window.root.mapToGlobal(local.toPoint())
    event=QWheelEvent(local,QPointF(global_pos),QPoint(0,pixels),QPoint(0,angle),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate if pixels else Qt.NoScrollPhase,False)
    QCoreApplication.sendEvent(window.root,event)

def prepare(window,qapp,tmp_path):
    window.history_page.set_records([_record(tmp_path,str(i),TaskStatus.COMPLETED) for i in range(100)])
    window._select_page(1);run_frames(qapp)
    return find_item(window,'historyList')

def test_wheel_reversal_interrupts_previous_target(quick_window,qapp,tmp_path):
    view=prepare(quick_window,qapp,tmp_path)
    wheel(quick_window,view,-720)
    run_frames(qapp,60)
    intermediate=view.property('contentY')
    assert intermediate>0
    wheel(quick_window,view,720)
    run_frames(qapp,260)
    assert view.property('contentY') < intermediate
    assert abs(view.property('contentY')) < 1

def test_pixel_scroll_takes_over_without_queued_wheel_motion(quick_window,qapp,tmp_path):
    view=prepare(quick_window,qapp,tmp_path)
    wheel(quick_window,view,-720);run_frames(qapp,50)
    before=view.property('contentY')
    wheel(quick_window,view,pixels=-20)
    after=view.property('contentY')
    assert after>before
    run_frames(qapp,240)
    assert abs(view.property('contentY')-after)<1

def test_reduced_motion_disables_wheel_smoothing(quick_window,qapp,tmp_path):
    view=prepare(quick_window,qapp,tmp_path)
    quick_window.set_reduce_motion(True)
    wheel(quick_window,view,-120)
    immediate=view.property('contentY')
    assert immediate>0
    run_frames(qapp,220)
    assert abs(view.property('contentY')-immediate)<1

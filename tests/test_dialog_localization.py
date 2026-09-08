from PySide6.QtCore import QObject, Qt
from PySide6.QtTest import QTest
from yt_downloader.core.errors import AppError
from yt_downloader.ui.quick_dialogs import ErrorSession
from yt_downloader.ui.localization import ACTION_TEXT, install_qt_zh_cn_translator
from conftest import run_frames, find_item, click_item

def test_all_application_dialog_actions_are_localized(quick_window,qapp):
    session = quick_window.dialogs.confirm('删除历史记录','只删除记录，文件会保留。','删除记录',lambda _:None)
    run_frames(qapp)
    popup = find_item(quick_window,'dialog-confirm')
    assert popup.property('visible') and popup.property('opened')
    buttons = [x for x in popup.findChildren(QObject) if x.property('text') is not None and x.property('visible')]
    labels = {x.property('text') for x in buttons}
    assert {'取消','删除记录'} <= labels
    assert labels.isdisjoint({'Cancel','OK','Delete','Close'})
    session.reject()

def test_action_map_covers_required_dialog_verbs():
    assert ACTION_TEXT == {'cancel':'取消','ok':'确定','close':'关闭','retry':'重试','open':'打开','delete':'删除'}

def test_qt_simplified_chinese_translation_is_available(qapp):
    assert install_qt_zh_cn_translator(qapp)

def test_update_error_dialog_retry_copy_close(quick_window,qapp):
    retries=[]
    dialog=ErrorSession(AppError('update','更新失败','detail'),'report',quick_window,title_text='更新失败',retry_callback=lambda:retries.append(True))
    dialog.show(); run_frames(qapp)
    popup=find_item(quick_window,'dialog-error')
    buttons=[x for x in popup.findChildren(QObject) if x.property('visible') and x.property('text')]
    assert {'重试','复制错误报告','关闭'} <= {x.property('text') for x in buttons}
    click_item(quick_window,next(x for x in buttons if x.property('text')=='重试'))
    dialog.retry()
    assert retries == [True]

def test_escape_cancels_once_and_restores_input_focus(quick_window,qapp):
    field=find_item(quick_window,'urlInput');field.forceActiveFocus()
    results=[]
    session=quick_window.dialogs.confirm('删除','确定？','删除',results.append)
    run_frames(qapp)
    assert find_item(quick_window,'dialog-confirm').property('opened')
    QTest.keyClick(quick_window.root,Qt.Key_Escape)
    run_frames(qapp)
    assert results == [False]
    assert field.hasActiveFocus()

def test_dialog_stack_preserves_existing_session(quick_window,qapp):
    first=ErrorSession(AppError('one','one','detail'),'report',quick_window)
    first.show();run_frames(qapp)
    original=find_item(quick_window,'dialog-error')
    second=quick_window.dialogs.confirm('确认','继续？','继续',lambda _:None)
    run_frames(qapp)
    assert find_item(quick_window,'dialog-error') is original
    second.reject();run_frames(qapp)
    assert original.property('opened') and first.state['open']

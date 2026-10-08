from conftest import find_item,run_frames
from yt_downloader.ui.quick_browser_companion import BrowserCompanionPresenter

def test_browser_toolbox_navigation_help_and_live_translation(quick_window,qapp):
    w=quick_window
    assert not find_item(w,'browserCompanionLoader').property('active')
    w._select_page(2)
    w.toolbox_page.selectCategory(2)
    run_frames(qapp,220)
    assert find_item(w,'browserCompanionPanel').isVisible()
    assert find_item(w,'browser-install-chrome').isEnabled()
    w.browser_companion.toggleHelp()
    assert w.browser_companion.state['helpVisible']
    w.i18n.setLanguage('ru-RU')
    run_frames(qapp,100)
    assert find_item(w,'browser-test-edge').property('text')==w.i18n.text('browser.test')
    assert not w.i18n.validateCoverage()
    assert not w.qml_warnings
    w.toolbox_page.requestTool() # Browser page cannot start thumbnail/subtitle jobs.
    assert not w.toolbox_page.state['toolBusy']
    w.toolbox_page.selectCategory(0)
    run_frames(qapp,220)
    assert not find_item(w,'browserCompanionPanel').isVisible()
    assert find_item(w,'browserCompanionLoader').property('active')

def test_registration_is_not_connection_and_local_probe_is_honest(qapp):
    class Manager:
        def status(self,b):return 'configured'
        def load(self):return {'browsers':{}}
        def identity(self,b):return b
    from yt_downloader.ui.localization import Translator
    p=BrowserCompanionPresenter(Translator(),manager=Manager())
    assert all(row['statusKey']=='browser.configured' for row in p.state['rows'])
    p.mark_seen('chrome')
    assert p.state['rows'][0]['statusKey']=='browser.connected'
    assert p.state['rows'][1]['statusKey']=='browser.configured'
    p.seen['chrome']-=301;p.refresh()
    assert p.state['rows'][0]['statusKey']=='browser.configured'
    p.close()


def test_connection_refresh_preserves_card_and_field_focus(quick_window, qapp, monkeypatch):
    from PySide6.QtCore import Qt
    import shiboken6
    w=quick_window
    w._select_page(2);w.toolbox_page.selectCategory(2)
    run_frames(qapp,220)
    field=find_item(w,'browser-id-chrome')
    field.forceActiveFocus(Qt.OtherFocusReason)
    monkeypatch.setattr(w.browser_companion.manager,'status',lambda browser:'configured')
    w.browser_companion.mark_seen('chrome')
    run_frames(qapp,80)
    assert shiboken6.isValid(field)
    assert find_item(w,'browser-id-chrome') is field
    assert field.hasActiveFocus()
    assert w.browser_companion.state['rows'][0]['statusKey']=='browser.connected'

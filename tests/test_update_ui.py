from conftest import find_item, run_frames
from conftest import click_item
from yt_downloader import __version__


def test_about_owns_manual_check_and_uses_real_version(quick_window, qtbot, qapp):
    quick_window._select_page(3)
    run_frames(qapp)
    button = find_item(quick_window, 'aboutUpdateAction')
    assert quick_window.state['version'] == __version__
    assert not hasattr(quick_window.settings_page, 'update_check_requested')
    with qtbot.waitSignal(quick_window.check_update_requested, timeout=500):
        click_item(quick_window, button)
    quick_window.set_update_state('正在检查…', busy=True)
    run_frames(qapp)
    assert not button.property('enabled')

def test_settings_page_has_stable_update_controls_and_persists_checkbox(quick_window):
    page = quick_window.settings_page
    assert not page.current_settings().auto_check_updates
    page.edit('auto_check_updates', True)
    assert page.current_settings().auto_check_updates

def test_main_window_uses_non_modal_update_banner(quick_window):
    quick_window.show_update_available('0.4.1')
    assert quick_window.state['updateVisible']
    assert '0.4.1' in quick_window.state['updateText']
    assert not quick_window.dialogs.sessions
    quick_window.hideUpdate()
    assert not quick_window.state['updateVisible']

from conftest import find_item, run_frames

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

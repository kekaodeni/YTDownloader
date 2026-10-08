from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from conftest import click_item, find_item, run_frames
from test_browser_onboarding import isolated_manager, open_browser, reveal
from yt_downloader.core.models import SUPPORTED_LOCALES


def test_inactive_install_guide_does_not_reserve_layout_in_other_dialogs(quick_window, qapp):
    w = quick_window
    w.dialogs.info('Information', 'Message')
    run_frames(qapp, 250)
    loader = find_item(w, 'browserGuideLoader')
    assert not loader.property('active')
    assert not loader.isVisible()
    assert find_item(w, 'dialog-info').property('width') == 620


def test_separate_install_guide_preserves_background_selection_and_scroll(quick_window, qapp, tmp_path):
    w = quick_window
    isolated_manager(w, tmp_path)
    open_browser(w, qapp, 'firefox')
    entry = find_item(w, 'browser-install-guide')
    scroll = reveal(w, qapp, entry)
    before = (scroll.property('contentY'), scroll.property('contentHeight'))
    click_item(w, entry)
    run_frames(qapp, 250)
    assert entry.property('appearance') == 'quiet'
    guide = w.browser_companion._guide
    assert guide.state['browser'] == 'firefox'
    assert find_item(w, 'guide-browser-instructions').property('text') == w.i18n.text('browser.install_firefox')
    click_item(w, find_item(w, 'guide-browser-edge'))
    run_frames(qapp, 100)
    assert guide.state['browser'] == 'edge'
    assert w.browser_companion.state['activeBrowser'] == 'firefox'
    assert find_item(w, 'guide-browser-instructions').property('text') == w.i18n.text('browser.install_edge')
    QTest.keyClick(w.root, Qt.Key_Escape)
    run_frames(qapp, 260)
    assert w.browser_companion._guide is None
    assert before == (scroll.property('contentY'), scroll.property('contentHeight'))
    assert w.browser_companion.state['activeBrowser'] == 'firefox'
    assert not w.qml_warnings


def test_install_guide_live_translation_has_all_ten_languages(quick_window, qapp, tmp_path):
    w = quick_window
    isolated_manager(w, tmp_path)
    open_browser(w, qapp, 'chrome')
    click_item(w, find_item(w, 'browser-install-guide'))
    run_frames(qapp, 240)
    for locale in SUPPORTED_LOCALES:
        w.i18n.setLanguage(locale)
        run_frames(qapp, 100)
        assert not w.i18n.validateCoverage()
        assert w.browser_companion._guide.state['title'] == w.i18n.text('browser.guide_title')
        assert find_item(w, 'guide-browser-instructions').property('text') == w.i18n.text('browser.install_chrome')
    QTest.keyClick(w.root, Qt.Key_Escape)
    run_frames(qapp, 260)
    assert not w.qml_warnings


def test_repaired_host_cannot_claim_relocated_extension_connected(quick_window, qapp, tmp_path):
    w = quick_window
    manager = isolated_manager(w, tmp_path)
    manager.install('chrome')
    old = manager.root / 'extensions/chrome'
    old.mkdir(parents=True)
    (old / 'user.txt').write_text('keep', 'utf-8')
    config = manager.load()
    config['browsers']['chrome'].pop('extension_path')
    manager._write(manager.config_path, config)
    manager.install('chrome')
    w.browser_companion.mark_seen('chrome')
    open_browser(w, qapp, 'chrome')
    row = w.browser_companion.state['rows'][0]
    assert row['extensionReload'] and not row['connected']
    assert row['statusKey'] == 'browser.reload_required'
    button = find_item(w, 'browser-confirm-reload-chrome')
    reveal(w, qapp, button)
    click_item(w, button)
    run_frames(qapp, 150)
    row = w.browser_companion.state['rows'][0]
    assert not row['extensionReload'] and not row['connected']
    w.browser_companion.mark_seen('chrome')
    assert w.browser_companion.state['rows'][0]['connected']
    assert (old / 'user.txt').read_text('utf-8') == 'keep'
    assert not w.qml_warnings

from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

from conftest import click_item, find_item, run_frames
from test_browser_guide_bounds import open_guide, bounds, edge_measurements, geometry


def test_browser_tabs_remain_visible_and_fixed_while_guide_body_scrolls(quick_window, qapp, tmp_path):
    w = quick_window
    dialog, scroll, view, _ = open_guide(w, qapp, tmp_path)
    tabs = [find_item(w, 'guide-browser-' + browser) for browser in ('chrome', 'edge', 'firefox')]
    initial = [geometry(tab) for tab in tabs]
    footer = geometry(dialog.property('footer'))
    title = find_item(w, 'guideTitle')
    title_bottom = title.mapToScene(QPointF(0, title.height())).y()
    assert 0 <= initial[0][1] - title_bottom <= 24
    edge_measurements(w, qapp, view, 'bottom')
    assert [geometry(tab) for tab in tabs] == initial
    assert geometry(dialog.property('footer')) == footer
    for tab in tabs:
        y = tab.mapToScene(QPointF()).y()
        assert y + tab.height() <= view.mapToScene(QPointF()).y()
    assert not w.qml_warnings


def test_guide_more_information_reaches_last_line_and_keeps_same_dialog(quick_window, qapp, tmp_path):
    w = quick_window
    dialog, scroll, view, _ = open_guide(w, qapp, tmp_path)
    instance = w.browser_companion._guide
    before = geometry(dialog)
    edge_measurements(w, qapp, view, 'bottom', count=1)
    click_item(w, find_item(w, 'guideMore'))
    run_frames(qapp, 100)
    assert find_item(w, 'guideDetails').isVisible()
    edge_measurements(w, qapp, view, 'bottom')
    last = find_item(w, 'guideLastLine')
    assert 0 <= last.mapToItem(view, QPointF()).y()
    assert last.mapToItem(view, QPointF(0, last.height())).y() <= view.height()
    for browser in ('edge', 'firefox', 'chrome'):
        click_item(w, find_item(w, 'guide-browser-' + browser))
        run_frames(qapp, 100)
        assert w.browser_companion._guide is instance
        assert geometry(dialog) == before
        assert view.property('contentY') == bounds(view)[0]
    click_item(w, find_item(w, 'guideHeaderClose'))
    run_frames(qapp, 250)
    assert w.browser_companion._guide is None
    click_item(w, find_item(w, 'browser-install-guide'))
    run_frames(qapp, 250)
    assert not find_item(w, 'guideDetails').isVisible()
    assert not w.qml_warnings


def test_guide_long_path_wraps_and_supports_keyboard_copy(quick_window, qapp, tmp_path):
    from test_browser_onboarding import isolated_manager, open_browser
    w = quick_window
    manager = isolated_manager(w, tmp_path)
    manager.bridge_path = tmp_path.joinpath(*(['portable-folder-with-a-long-name'] * 5), 'YTDownloaderBridge.exe')
    manager.bridge_path.parent.mkdir(parents=True)
    manager.bridge_path.write_bytes(b'controlled test host')
    w.browser_companion.refresh()
    open_browser(w, qapp, 'chrome')
    click_item(w, find_item(w, 'browser-install-guide'))
    run_frames(qapp, 250)
    path = find_item(w, 'guideExtensionPath')
    assert path.property('text') == w.browser_companion.state['rows'][0]['folderPath']
    assert path.property('contentWidth') <= path.width() - 20 + .1
    assert path.property('contentHeight') > 16
    assert path.height() >= path.property('contentHeight') + 20
    click_item(w, path)
    previous = QMimeData()
    clipboard_data = qapp.clipboard().mimeData()
    if clipboard_data:
        for mime_type in clipboard_data.formats():
            previous.setData(mime_type, clipboard_data.data(mime_type))
    try:
        QTest.keyClick(w.root, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClick(w.root, Qt.Key_C, Qt.ControlModifier)
        copied_path_matches = qapp.clipboard().text() == path.property('text')
        assert copied_path_matches, 'Selected extension path was not copied'
    finally:
        qapp.clipboard().setMimeData(previous)
    assert not w.qml_warnings


def test_install_guide_entry_has_help_icon_and_localized_accessible_label(quick_window, qapp, tmp_path):
    from test_browser_onboarding import isolated_manager, open_browser
    w = quick_window
    isolated_manager(w, tmp_path)
    open_browser(w, qapp, 'chrome')
    entry = find_item(w, 'browser-install-guide')
    expr = QQmlExpression(w.engine.rootContext(), entry, 'icon.source.toString()')
    icon, undefined = expr.evaluate()
    assert not undefined and icon.endswith('/icons/info_regular.svg')
    assert entry.height() >= 38 and entry.property('appearance') == 'quiet'
    assert entry.property('text') == w.i18n.text('browser.guide_entry') == '安装指南'
    name = QQmlExpression(QQmlEngine.contextForObject(entry), entry, 'Accessible.name')
    value, undefined = name.evaluate()
    assert not undefined and value == entry.property('text')
    QTest.keyClick(w.root, Qt.Key_Tab)
    entry.forceActiveFocus()
    QTest.keyClick(w.root, Qt.Key_Space)
    run_frames(qapp, 250)
    assert w.browser_companion._guide is not None
    assert not w.qml_warnings

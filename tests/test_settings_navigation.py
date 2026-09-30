from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlProperty

from conftest import click_item, find_item, run_frames
import pytest


def test_settings_starts_with_appearance_and_has_no_selected_focus_outline(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    assert find_item(quick_window, 'languageCombo').isVisible()
    assert not find_item(quick_window, 'defaultDownloadProfile').isVisible()
    click_item(quick_window, find_item(quick_window, 'settingsNav-4'))
    run_frames(qapp)
    assert QQmlProperty.read(find_item(quick_window, 'settingsNav-4').property('background'), 'border.width') == 0


def test_settings_has_keyboard_secondary_navigation_and_one_category(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    page = find_item(quick_window, 'settingsPage')
    nav = find_item(quick_window, 'settingsNavigation')
    assert nav.property('count') == 6
    assert page.property('category') == 0
    assert find_item(quick_window, 'languageCombo').isVisible()
    click_item(quick_window, find_item(quick_window, 'settingsNav-3'))
    run_frames(qapp)
    assert page.property('category') == 3
    assert not find_item(quick_window, 'defaultDownloadProfile').isVisible()
    assert not find_item(quick_window, 'proxyInput').isVisible()
    quick_window.settings_page.setSetting('proxy_mode', 'custom')
    run_frames(qapp)
    assert find_item(quick_window, 'proxyInput').isVisible()
    QTest.keyClick(quick_window.root, Qt.Key_Down)
    QTest.keyClick(quick_window.root, Qt.Key_Return)
    run_frames(qapp)
    assert page.property('category') == 4
    assert find_item(quick_window, 'autoCheckUpdates').isVisible()
    assert not find_item(quick_window, 'proxyInput').isVisible()
    QTest.keyClick(quick_window.root, Qt.Key_Tab)
    run_frames(qapp, 50)
    assert not nav.hasActiveFocus()


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('locale', ['zh-CN', 'ru-RU', 'es-ES'])
def test_settings_categories_preserve_navigation_and_wrap_rows(quick_window, qapp, theme, locale):
    quick_window.root.resize(600, 700)
    quick_window._select_page(2)
    quick_window.theme.set_mode(theme)
    quick_window.i18n.setLanguage(locale)
    run_frames(qapp, 350)
    nav = find_item(quick_window, 'settingsNavigation')
    from PySide6.QtCore import QPointF
    position = nav.mapToScene(QPointF())
    for category in range(6):
        quick_window.settings_page.selectCategory(category)
        run_frames(qapp, 240)
        for index in range(6):
            assert find_item(quick_window, f'settingsCategory-{index}').isVisible() == (index == category)
        scroll = find_item(quick_window, 'settingsScroll')
        scroll.setProperty('contentY', max(0, scroll.property('contentHeight') - scroll.height()))
        run_frames(qapp, 80)
        assert nav.mapToScene(QPointF()) == position
        scroll.setProperty('contentY', 0)
    assert quick_window.settings_page.state['ffmpegVersion']
    assert quick_window.settings_page.state['ffmpegPath'].endswith('ffmpeg.exe')


def test_open_cookie_settings_selects_cookie_category(quick_window, qapp):
    quick_window.openCookieSettings()
    run_frames(qapp)
    assert quick_window.settings_page.state['category'] == 2
    assert find_item(quick_window, 'cookieProfiles').isVisible()


@pytest.mark.parametrize('reduced', [False, True])
def test_main_and_settings_share_sliding_selected_surface(quick_window, qapp, reduced):
    quick_window.settings_page.setSetting('reduce_motion', reduced)
    main = find_item(quick_window, 'mainNavigation-selection')
    quick_window._select_page(1)
    run_frames(qapp, 60)
    if reduced:
        assert main.y() == 49
    else:
        assert 0 < main.y() < 49
    quick_window._select_page(2)
    run_frames(qapp)
    selected = find_item(quick_window, 'settingsNavigation-selection')
    quick_window.settings_page.selectCategory(4)
    target = find_item(quick_window, 'settingsNav-4').y()
    run_frames(qapp, 60)
    assert selected.y() == target if reduced else 0 < selected.y() < target
    run_frames(qapp, 300)
    assert selected.y() == target
    assert main.property('color') == selected.property('color')
    assert main.property('radius') == selected.property('radius') == 9
    assert QQmlProperty.read(selected, 'border.width') == 0
    assert find_item(quick_window, 'nav-0').metaObject().className() == find_item(quick_window, 'settingsNav-0').metaObject().className()

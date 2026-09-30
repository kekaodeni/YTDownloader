from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
import pytest

from conftest import click_item, find_item, run_frames


def test_keyboard_selection_without_opening_popup_refreshes_locale(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    combo.forceActiveFocus()
    QTest.keyClick(quick_window.root, Qt.Key_Down)
    run_frames(qapp, 120)
    assert quick_window.i18n.currentLocale == 'zh-TW'
    assert not find_item(quick_window, 'popup-languageCombo').property('visible')


def test_keyboard_type_search_reveals_option_without_hover_scrolling(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    click_item(quick_window, combo)
    run_frames(qapp, 160)
    QTest.keyClick(quick_window.root, Qt.Key_P)
    run_frames(qapp, 100)
    view = find_item(quick_window, 'options-languageCombo')
    option = find_item(quick_window, 'languageCombo-option-7')
    y = option.mapToItem(view, QPointF()).y()
    assert 0 <= y <= view.height()-option.height()+1
    QTest.keyClick(quick_window.root, Qt.Key_Return)
    run_frames(qapp, 220)
    assert quick_window.i18n.currentLocale == 'pt-BR'


def test_language_hover_does_not_reposition_or_change_popup(quick_window, qapp):
    quick_window._select_page(2)
    quick_window.settings_page.setSetting('language', 'th-TH')
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    click_item(quick_window, combo)
    run_frames(qapp, 220)
    popup = find_item(quick_window, 'popup-languageCombo')
    view = popup.property('contentItem')
    before = view.property('contentY')
    languages = quick_window.i18n.languages
    for dy in (1, 12, 90, 180, 40, 210, 1):
        point = view.mapToScene(QPointF(30, dy)).toPoint()
        QTest.mouseMove(quick_window.root, point)
        run_frames(qapp, 40)
        assert view.property('contentY') == before
        assert combo.property('count') == 10
        assert combo.property('currentIndex') == 9
        assert quick_window.i18n.languages == languages


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_all_ten_languages_can_be_selected_and_reopened_with_native_names(quick_window, qapp, mode):
    quick_window._select_page(2)
    quick_window.theme.set_mode(mode)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    languages = quick_window.i18n.languages
    names = [language['name'] for language in languages]
    for index, language in enumerate(languages):
        click_item(quick_window, combo)
        run_frames(qapp, 160)
        assert combo.property('model') == names
        QTest.keyClick(quick_window.root, Qt.Key_Home)
        for _ in range(index):
            QTest.keyClick(quick_window.root, Qt.Key_Down)
        run_frames(qapp, 80)
        view = find_item(quick_window, 'options-languageCombo')
        item = find_item(quick_window, f'languageCombo-option-{index}')
        y = item.mapToItem(view, QPointF()).y()
        assert -1 <= y <= view.height() - item.height() + 1
        QTest.keyClick(quick_window.root, Qt.Key_Return)
        run_frames(qapp, 220)
        assert quick_window.i18n.currentLocale == language['locale']
        assert combo.property('model') == names


def test_language_refresh_waits_until_popup_finishes_closing(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    combo = find_item(quick_window, 'languageCombo')
    click_item(quick_window, combo)
    run_frames(qapp, 180)
    QTest.keyClick(quick_window.root, Qt.Key_Down)
    QTest.keyClick(quick_window.root, Qt.Key_Return)
    assert quick_window.i18n.currentLocale == 'zh-CN'
    run_frames(qapp, 240)
    assert quick_window.i18n.currentLocale == 'zh-TW'
    assert not find_item(quick_window, 'popup-languageCombo').property('visible')

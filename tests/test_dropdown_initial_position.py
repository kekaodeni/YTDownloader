import pytest
from PySide6.QtCore import QPointF, Qt, QTimer, QElapsedTimer
from PySide6.QtTest import QTest

from conftest import click_item, find_item, run_frames


def wait_popup_transition(qapp, popup, opened):
    """Wait for the real transition endpoint, without retrying input.

    A 140 ms exit animation starts on a rendered frame; a 150 ms sleep can
    leave it visible and make the next click close it instead of reopen it.
    """
    elapsed = QElapsedTimer()
    elapsed.start()
    while elapsed.elapsed() < 1500:
        if popup.property('opened') if opened else not popup.property('visible'):
            return
        run_frames(qapp, 20)
    assert popup.property('opened') if opened else not popup.property('visible')


def test_keyboard_highlight_scrolls_without_changing_selection_until_enter(quick_window, qapp):
    w = quick_window
    w._select_page(3)
    w.settings_page.setSetting('language', 'ja-JP')
    run_frames(qapp, 200)
    combo = find_item(w, 'languageCombo')
    click_item(w, combo); run_frames(qapp, 180)
    QTest.keyClick(w.root, Qt.Key_End); run_frames(qapp, 80)
    assert combo.property('highlightedIndex') == 9
    assert combo.property('currentIndex') == 3 and w.i18n.currentLocale == 'ja-JP'
    view = find_item(w, 'options-languageCombo')
    assert view.property('contentY') > view.property('originY')
    assert find_item(w, 'languageCombo-option-3').property('selectedOption')
    QTest.keyClick(w.root, Qt.Key_Home); run_frames(qapp, 80)
    assert combo.property('highlightedIndex') == 0 and combo.property('currentIndex') == 3
    QTest.keyClick(w.root, Qt.Key_Down); run_frames(qapp, 80)
    assert combo.property('highlightedIndex') == 1
    QTest.keyClick(w.root, Qt.Key_Return); run_frames(qapp, 250)
    assert w.i18n.currentLocale == 'zh-TW' and combo.property('currentIndex') == 1


def test_open_popup_language_refresh_preserves_scroll_and_selection(quick_window, qapp):
    w = quick_window
    w._select_page(3)
    w.settings_page.setSetting('theme', 'light')
    run_frames(qapp, 200)
    combo = find_item(w, 'themeCombo')
    click_item(w, combo); run_frames(qapp, 160)
    view = find_item(w, 'options-themeCombo')
    before = view.property('contentY')
    w.i18n.setLanguage('ru-RU'); run_frames(qapp, 100)
    assert combo.property('currentIndex') == 1 and view.property('contentY') == before
    assert combo.property('model')[0] == w.i18n.text('settings.theme_system')


@pytest.mark.parametrize('reduce_motion', [False, True])
def test_user_scrolling_and_hover_do_not_reset_initial_viewport(quick_window, qapp, reduce_motion):
    from test_quick_scroll import wheel
    w = quick_window
    w._select_page(3);w.set_reduce_motion(reduce_motion);run_frames(qapp,200)
    combo = find_item(w,'languageCombo')
    click_item(w,combo)
    popup = find_item(w, 'popup-languageCombo')
    wait_popup_transition(qapp, popup, True)
    view=find_item(w,'options-languageCombo')
    for _ in range(20):wheel(w,view,angle=-120)
    run_frames(qapp,400)
    assert view.property('contentY') > view.property('originY')
    before=view.property('contentY')
    row=find_item(w,'languageCombo-option-4')
    assert popup.property('opened')
    point = row.mapToScene(QPointF(10,row.height()/2)).toPoint()
    state_before = (popup.property('visible'), view.width(), view.height(),
                    combo.property('currentIndex'), combo.property('highlightedIndex'),
                    view.property('flicking'), view.property('initializingViewport'), point)
    QTest.mouseMove(w.root,point)
    run_frames(qapp,100)
    state_after = (popup.property('visible'), view.width(), view.height(),
                   combo.property('currentIndex'), combo.property('highlightedIndex'),
                   view.property('flicking'), view.property('initializingViewport'))
    assert popup.property('opened'), (state_before, state_after)
    assert view.property('contentY') == pytest.approx(before, abs=.5), (state_before, state_after)
    assert abs(view.property('elasticOffset')) <= .1
    assert combo.property('currentIndex') == 0


@pytest.mark.parametrize('index', [1, 5, 9])
def test_mouse_reopen_starts_at_top_without_changing_language(quick_window, qapp, index):
    w = quick_window
    w._select_page(3)
    locales = [row['locale'] for row in w.i18n.languages]
    w.settings_page.setSetting('language', locales[index])
    run_frames(qapp, 220)
    combo = find_item(w, 'languageCombo')
    for _ in range(2):
        click_item(w, combo)
        run_frames(qapp, 180)
        view = find_item(w, 'options-languageCombo')
        assert view.property('contentY') == pytest.approx(view.property('originY'), abs=.1)
        assert combo.property('currentIndex') == index
        assert w.i18n.currentLocale == locales[index]
        view.setProperty('contentY', view.property('originY') + max(0, view.property('contentHeight') - view.height()))
        run_frames(qapp, 100)
        QTest.keyClick(w.root, Qt.Key_Escape)
        run_frames(qapp, 180)


def test_mouse_open_has_no_old_position_frame(quick_window, qapp):
    w = quick_window
    w._select_page(3)
    w.settings_page.setSetting('language', 'th-TH')
    run_frames(qapp, 200)
    view = find_item(w, 'options-languageCombo')
    observed = []
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.timeout.connect(lambda: observed.append(view.property('contentY') - view.property('originY')))
    timer.start(4)
    click_item(w, find_item(w, 'languageCombo'))
    run_frames(qapp, 180)
    timer.stop()
    assert observed and max(abs(value) for value in observed) < .1


@pytest.mark.parametrize('selector', ['quality', 'batch', 'language', 'profile', 'proxy', 'remux', 'content'])
def test_shared_application_selectors_keep_values_when_mouse_reopened(quick_window, qapp, tmp_path, selector):
    from dataclasses import replace
    from test_download_service import _request
    from yt_downloader.services.media_metadata import resolve_metadata
    w = quick_window
    w.root.resize(1260, 900)
    if selector in {'profile', 'proxy', 'language'}:
        w._select_page(3)
        if selector == 'profile':
            w.settings_page.selectCategory(1)
            w.settings_page.setDefaultProfile('best')
            name = 'defaultDownloadProfile'
        elif selector == 'proxy':
            w.settings_page.selectCategory(3)
            w.settings_page.setSetting('proxy_mode', 'custom')
            name = 'proxyMode'
        else:
            w.settings_page.setSetting('language', 'ja-JP')
            name = 'languageCombo'
        run_frames(qapp, 240)
        scroll = find_item(w, 'settingsScroll')
    else:
        page = w.download_page
        if selector == 'batch':
            media = resolve_metadata({'_type': 'playlist', 'title': 'List', 'entries': [
                {'title': 'One', 'url': 'https://example.org/1'}]}, 'https://example.org/list')
            page.show_video(media)
            page.selectCollectionQuality(3)
            name = 'collectionQualityCombo'
        else:
            video = _request(tmp_path).video
            video = replace(video, formats=tuple(replace(video.formats[0], label=f'{h}p', height=h,
                format_selector=str(h), video_format_id=str(h)) for h in [2160, 1440, 1080]))
            page.show_video(video)
            if selector == 'content':
                page.selectMode('video_only');name='modeCombo'
            elif selector == 'remux':
                page.setAdvancedToggle('advancedExpanded', True)
                page.setAdvancedField('remuxContainer', 'mp4');name='remuxContainer'
            else:
                page.selectFormat(1);name='formatCombo'
        run_frames(qapp, 650 if selector == 'remux' else 250)
        scroll = find_item(w, 'taskList')
    combo = find_item(w, name)
    content = scroll.property('contentItem')
    y = combo.mapToItem(content, QPointF()).y()
    top = scroll.property('originY')
    bottom = top + max(0, scroll.property('contentHeight') - scroll.height())
    scroll.setProperty('contentY', max(top, min(y - 80, bottom)))
    run_frames(qapp, 140)
    selected = combo.property('currentIndex')
    assert selected > 0
    point = combo.mapToScene(QPointF(combo.width()/2, combo.height()/2))
    assert combo.isVisible() and combo.isEnabled()
    assert 0 <= point.y() < w.root.height(), (selector, point, top, bottom)
    for _ in range(2):
        click_item(w, combo)
        popup = find_item(w, 'popup-' + name)
        wait_popup_transition(qapp, popup, True)
        view = find_item(w, 'options-' + name)
        assert popup.property('visible')
        assert view.property('contentY') == pytest.approx(view.property('originY'), abs=.1)
        assert combo.property('currentIndex') == selected
        assert find_item(w, name + '-option-' + str(selected)).property('selectedOption')
        QTest.keyClick(w.root, Qt.Key_Escape)
        wait_popup_transition(qapp, popup, False)
    assert not w.qml_warnings


def test_all_application_comboboxes_use_the_shared_viewport_policy():
    import re
    from pathlib import Path
    qml = Path(__file__).resolve().parents[1] / 'src/yt_downloader/ui/qml'
    raw = [p.name for p in qml.glob('*.qml') if re.search(r'\bComboBox\s*\{', p.read_text('utf-8'))]
    assert raw == ['UiCombo.qml']
    assert re.search(r'\bUiCombo\s*\{', (qml/'UiLanguageCombo.qml').read_text('utf-8'))

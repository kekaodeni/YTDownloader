from PySide6.QtCore import QPointF
from conftest import find_item, run_frames


def test_toolbox_input_controls_fit_compact_and_long_languages(quick_window, qapp):
    window = quick_window
    window.root.setWidth(500)
    window._select_page(2)
    for language in ('zh-CN', 'ru-RU', 'es-ES', 'pt-BR'):
        window.i18n.setLanguage(language)
        run_frames(qapp)
        scroll = find_item(window, 'toolboxScroll')
        for name in ('toolbox-parseButton', 'toolbox-cookieManagementButton', 'toolbox-useCookieSwitch'):
            item = find_item(window, name)
            right = item.mapToItem(scroll, QPointF(item.width(), 0)).x()
            assert right <= scroll.width() + 1, (language, name, right, scroll.width())


def test_toolbox_subtitle_row_toggle_once_and_indicator_size(quick_window, qapp):
    from conftest import click_item
    from yt_downloader.services.media_metadata import resolve_metadata
    window = quick_window
    window.toolbox_page.show_video(resolve_metadata(dict(id='one', title='One', subtitles={
        'en': [dict(ext='srt', data='Subtitle')]}), 'https://example.org/video'))
    window._select_page(2)
    window.toolbox_page.selectCategory(1)
    run_frames(qapp)
    row = find_item(window, 'toolbox-subtitle-en')
    indicator = row.property('indicator')
    assert indicator.width() == indicator.height() == 20
    click_item(window, row)
    run_frames(qapp)
    assert window.toolbox_page.state['toolSubtitleLanguages'] == ['en']
    click_item(window, row)
    run_frames(qapp)
    assert window.toolbox_page.state['toolSubtitleLanguages'] == []


def test_archive_clear_button_wraps_long_language_in_compact_settings(quick_window, qapp):
    window = quick_window
    window.root.setWidth(500)
    window._select_page(3)
    window.settings_page.selectCategory(1)
    for language in ('ru-RU', 'es-ES', 'pt-BR'):
        window.i18n.setLanguage(language)
        run_frames(qapp)
        button = find_item(window, 'clearDownloadArchive')
        assert button.width() <= button.parentItem().width() + 1

from yt_downloader.ui.localization import Translator
from conftest import find_item, run_frames
from yt_downloader.core.models import HistoryRecord, SUPPORTED_LOCALES, TASK_STATUS_MESSAGE_IDS, TaskStatus
from pathlib import Path
import re
import pytest


def test_translator_exposes_ten_native_named_languages(qapp):
    translator = Translator('zh-CN')

    assert [item['locale'] for item in translator.languages] == [
        'zh-CN', 'zh-TW', 'en-US', 'ja-JP', 'ko-KR',
        'ru-RU', 'es-ES', 'pt-BR', 'vi-VN', 'th-TH',
    ]
    assert [item['name'] for item in translator.languages] == [
        '简体中文', '繁體中文', 'English', '日本語', '한국어',
        'Русский', 'Español', 'Português', 'Tiếng Việt', 'ไทย',
    ]


def test_translator_switches_language_and_formats_parameters(qapp):
    translator = Translator('zh-CN')
    changes = []
    translator.languageChanged.connect(changes.append)

    translator.setLanguage('en-US')

    assert translator.currentLocale == 'en-US'
    assert changes == ['en-US']
    assert translator.text('settings.language') == 'Language'
    assert translator.text('history.selected_count', {'count': 3}) == '3 selected'


def test_task_action_labels_are_distinct_from_status_copy_in_all_locales(qapp):
    translator = Translator('zh-CN')
    messages_by_locale = {}
    for locale in ('zh-CN', 'zh-TW', 'en-US', 'ja-JP', 'ko-KR', 'ru-RU', 'es-ES', 'pt-BR', 'vi-VN', 'th-TH'):
        translator.setLanguage(locale)
        messages_by_locale[locale] = translator.messages
        messages = translator.messages
        assert messages['task.action.pause'] != messages['task.status.downloading_video']
        assert messages['task.action.resume'] != messages['task.status.paused']
        assert messages['task.action.cancel'] != messages['task.status.cancelling']

    assert messages_by_locale['zh-CN']['task.action.pause'] == '暂停'
    assert messages_by_locale['zh-CN']['task.action.resume'] == '继续'
    assert messages_by_locale['zh-TW']['task.action.resume'] == '繼續'
    assert messages_by_locale['zh-CN']['task.action.cancel'] == '取消'
    assert messages_by_locale['en-US']['task.action.pause'] == 'Pause'
    assert messages_by_locale['en-US']['task.action.resume'] == 'Resume'
    assert messages_by_locale['en-US']['task.action.cancel'] == 'Cancel'


def test_missing_translation_is_explicit_and_catalogs_are_complete(qapp):
    translator = Translator('ja-JP')

    assert translator.text('missing.example') == '[missing:missing.example]'
    assert translator.validateCoverage() == []


def test_every_static_qml_translation_reference_has_all_locale_values(qapp):
    translator = Translator('zh-CN')
    qml_dir = Path(__file__).parents[1] / 'src' / 'yt_downloader' / 'ui' / 'qml'
    referenced = set()
    for path in qml_dir.glob('*.qml'):
        source = path.read_text(encoding='utf-8')
        referenced.update(re.findall(r'i18n\.messages\["([^"]+)"\]', source))
    referenced.update(TASK_STATUS_MESSAGE_IDS.values())

    assert tuple(item['locale'] for item in translator.languages) == SUPPORTED_LOCALES
    assert referenced <= set(translator.messages)
    assert translator.validateCoverage() == []


def test_settings_language_switch_updates_live_qml_binding(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    language_field = find_item(quick_window, 'languageField')
    combo = find_item(quick_window, 'languageCombo')

    quick_window.settings_page.edit('language', 'en-US')
    run_frames(qapp)

    assert quick_window.i18n.currentLocale == 'en-US'
    assert language_field.property('label') == 'Language'
    assert combo.property('currentIndex') == 2
    assert combo.property('model')[:3] == ['简体中文', '繁體中文', 'English']
    profiles = quick_window.settings_page.state['profileOptions']
    assert [item['name'] for item in profiles] == ['Recommended', 'Highest quality']


def test_settings_text_field_calls_presenter_slot_without_qml_warning(quick_window, qapp):
    quick_window._select_page(2)
    run_frames(qapp)
    field = find_item(quick_window, 'defaultDirectory')

    field.setProperty('text', 'D:/localized-setting-test')
    run_frames(qapp, 50)

    assert quick_window.settings_page.state['download_directory'] == 'D:/localized-setting-test'
    assert quick_window.qml_warnings == []


def test_history_labels_switch_live_and_keep_external_title(quick_window, qapp, tmp_path):
    title = '어려워? 어렵냐고!'
    quick_window.history_page.set_records([HistoryRecord(
        task_id='localization-item', video_id='opaque', url='https://example.invalid/video',
        title=title, file_path=tmp_path / 'video.mp4', quality_label='1080p', file_size=123,
        thumbnail_path=None, status=TaskStatus.COMPLETED, created_at='2026-09-29',
    )])
    quick_window._select_page(1)
    run_frames(qapp)

    status = find_item(quick_window, 'historyStatus-localization-item')
    row_title = find_item(quick_window, 'historyTitle-localization-item')
    assert status.property('text') == '下载完成'
    assert row_title.property('text') == title

    quick_window.i18n.setLanguage('ru-RU')
    run_frames(qapp)

    assert status.property('text') == 'Загрузка завершена'
    assert row_title.property('text') == title


def test_download_advanced_options_retranslate_live(quick_window, qapp):
    from scripts.verify_quick_ui import sample_video

    quick_window.download_page.show_video(sample_video())
    quick_window.download_page.setAdvancedToggle('advancedExpanded', True)
    run_frames(qapp)
    quick_window.i18n.setLanguage('ja-JP')
    run_frames(qapp)

    assert find_item(quick_window, 'advancedOptionsToggle').property('label') == quick_window.i18n.messages['download.advanced']
    assert find_item(quick_window, 'clipEnabled').property('label') == quick_window.i18n.messages['clip.range_toggle']
    assert quick_window.i18n.messages['postprocess.title'] == 'ダウンロード後'


def test_technical_format_summary_retranslates_merge_hint(quick_window, qapp):
    from scripts.verify_quick_ui import sample_video

    quick_window.download_page.show_video(sample_video())
    summary = find_item(quick_window, 'technicalSummary')
    assert '需要自动合并' in summary.property('text')

    quick_window.i18n.setLanguage('ru-RU')
    run_frames(qapp)
    text = summary.property('text')
    assert 'требуется автоматическое объединение' in text
    assert not any('\u3400' <= char <= '\u9fff' for char in text)

    quick_window.i18n.setLanguage('es-ES')
    run_frames(qapp)
    assert 'Se requiere combinar automáticamente' in summary.property('text')


def test_download_cookie_state_and_settings_feedback_refresh_live(quick_window, qapp):
    from yt_downloader.core.models import CookieProfile

    quick_window.download_page.set_cookie_state((CookieProfile(
        'youtube', 'YouTube Firefox', 'browser', browser='firefox', domain_hint='youtube.com'),))
    quick_window.download_page.setField('url', 'https://www.youtube.com/watch?v=fixture')
    quick_window.download_page.setCookieEnabled(True)
    assert '待验证' in quick_window.download_page.state['cookieAuthStatus']
    quick_window.cookies.update(message='Cookie 配置已保存。')
    quick_window.settings_page.set_network_test_result(True, '连接成功（0.30 秒） · 直连（忽略系统代理）')
    run_frames(qapp)
    assert find_item(quick_window, 'cookieFeedback').property('text') == 'Cookie 配置已保存。'
    assert find_item(quick_window, 'networkFeedback').property('text') == '连接成功（0.30 秒） · 直连（忽略系统代理）'

    quick_window.i18n.setLanguage('ru-RU')
    run_frames(qapp)

    assert 'ожидают проверки' in quick_window.download_page.state['cookieAuthStatus']
    assert find_item(quick_window, 'cookieFeedback').property('text') == 'Профиль Cookie сохранён.'
    assert find_item(quick_window, 'networkFeedback').property('text') == 'Подключено за 0.30 с · Прямое соединение (системный прокси отключён)'
    quick_window.settings_page.edit('download_directory', 'D:/localized path')
    assert 'изменения' in quick_window.settings_page.state['saveText']


@pytest.mark.parametrize(('source', 'expected'), [
    ('Cookie 配置无法读取，已保持不使用；原文件未修改。', 'The cookie settings could not be read. Cookies remain disabled, and the original file was not changed.'),
    ('Cookie 使用偏好保存失败，原设置已保留。', 'Could not save the cookie preference. The previous setting was kept.'),
    ('当前运行环境不支持自动安装，请从发布页面手动升级。', 'Automatic installation is not supported in this environment. Update manually from the releases page.'),
    ('YT Downloader 0.6.0 更新', 'YT Downloader 0.6.0 update'),
    ('设置视频封面', 'Set video cover'),
    ('封面已写入视频，Windows Explorer 已识别该封面。', 'The cover was written, and Windows Explorer recognizes it.'),
])
def test_runtime_feedback_source_messages_are_catalogued(qapp, source, expected):
    translator = Translator('en-US')
    assert translator.sourceText(source) == expected


@pytest.mark.parametrize(('locale', 'theme'), [
    ('ru-RU', 'light'), ('ru-RU', 'dark'),
    ('es-ES', 'light'), ('es-ES', 'dark'),
    ('pt-BR', 'light'), ('pt-BR', 'dark'),
])
def test_long_localized_settings_copy_remains_in_layout(quick_window, qapp, locale, theme):
    quick_window.root.resize(540, 700)
    quick_window._select_page(2)
    quick_window.theme.set_mode(theme)
    quick_window.i18n.setLanguage(locale)
    quick_window.settings_page.selectCategory(3)
    run_frames(qapp)

    language_field = find_item(quick_window, 'languageField')
    assert language_field.property('label') == quick_window.i18n.messages['settings.language']
    assert language_field.width() > 0
    assert language_field.x() >= 0
    assert language_field.x() + language_field.width() <= quick_window.root.width()
    assert language_field.isVisible()
    quick_window.settings_page.selectCategory(0)
    run_frames(qapp)
    profile_row = find_item(quick_window, 'defaultProfileRow')
    assert profile_row.property('description') == quick_window.i18n.messages['settings.profile_explainer']
    assert profile_row.isVisible() and profile_row.width() > 0
    assert profile_row.height() >= 60


def test_updater_source_messages_refresh_live_and_keep_parameters(quick_window, qapp):
    quick_window.set_update_state('上次检查：2026-09-29 12:30')
    quick_window.i18n.setLanguage('es-ES')
    run_frames(qapp)

    assert quick_window.state['updateStatus'] == 'Última comprobación: 2026-09-29 12:30'
    quick_window.set_update_state('发现 0.6.0')
    assert quick_window.state['updateStatus'] == 'Se encontró 0.6.0'

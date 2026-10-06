from dataclasses import replace
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from yt_downloader.core.errors import AppError, CancellationCleanupReport
from yt_downloader.core.models import DownloadProgress, DownloadProfile, DownloadResult, ParseState, TaskStatus
from yt_downloader.ui.quick_dialogs import ErrorSession
from test_download_service import _request
from conftest import find_item, click_item, run_frames

def test_metadata_busy_state_disables_input_without_blocking(quick_window, qtbot):
    page = quick_window.download_page
    page.set_loading(True)
    assert not find_item(quick_window, 'urlInput').isEnabled()
    button = find_item(quick_window, 'parseButton')
    assert button.isEnabled() and button.property('text') == '取消解析'
    with qtbot.waitSignal(page.parse_cancel_requested):
        click_item(quick_window, button)
    assert page.parse_state is ParseState.CANCELLING
    assert not button.isEnabled()
    assert button.property('text') == quick_window.i18n.messages['download.stop_parsing']
    page.set_loading(False)
    assert find_item(quick_window, 'urlInput').isEnabled()

def test_metadata_busy_label_is_never_clipped_by_feedback_motion(quick_window, qapp):
    page = quick_window.download_page
    page.set_loading(True)
    run_frames(qapp, 80)
    button = find_item(quick_window, 'parseButton')
    assert button.width() >= button.property('implicitContentWidth') + 24
    page.requestParse()
    run_frames(qapp, 120)
    assert button.width() >= button.property('implicitContentWidth') + 24

def test_url_clear_action_is_centered_and_clears_presenter(quick_window, qapp):
    quick_window.download_page.set_url('https://youtu.be/dQw4w9WgXcQ')
    run_frames(qapp, 50)
    field = find_item(quick_window, 'urlInput')
    clear = find_item(quick_window, 'clearUrl')
    assert abs(clear.y() + clear.height()/2 - field.height()/2) < 1
    click_item(quick_window, clear)
    assert quick_window.download_page.state['url'] == ''


def test_advanced_clip_panel_is_collapsed_then_validates_immediately(quick_window, qapp):
    from scripts.verify_quick_ui import sample_video

    page = quick_window.download_page
    page.show_video(sample_video())
    assert page.state['advancedExpanded'] is False
    assert not find_item(quick_window, 'clipEnabled').isVisible()
    page.setAdvancedToggle('advancedExpanded', True)
    qapp.processEvents()
    assert page.state['advancedExpanded'] is True
    clip_toggle = find_item(quick_window, 'clipEnabled')
    assert clip_toggle.isVisible()
    page.setAdvancedToggle('clipEnabled', True)
    assert page.state['clipEnabled'] is True
    assert page.state['clipValid'] is True
    assert page.state['clipEnd'] == '12:46'

    start = find_item(quick_window, 'clipStart')
    end = find_item(quick_window, 'clipEnd')
    page.setAdvancedField('clipStart', '03:15')
    page.setAdvancedField('clipEnd', '05:40')
    assert page.state['clipValid'] is True
    page.setAdvancedField('clipEnd', '13:00')
    assert page.state['clipValid'] is False
    assert page.state['clipError'] == page._t('clip.end_after_duration')


def test_advanced_options_disclosure_and_fresh_defaults(quick_window, qapp):
    from scripts.verify_quick_ui import sample_video

    page = quick_window.download_page
    page.show_video(sample_video())
    header = find_item(quick_window, 'advancedOptionsToggle')
    panel = find_item(quick_window, 'advancedOptionsPanel')
    assert not panel.isVisible()
    assert header.property('implicitHeight') >= 40
    assert header.property('label') == quick_window.i18n.messages['download.advanced']
    assert page.state['embedThumbnail'] is False
    assert page.state['embedMetadata'] is False
    assert page.state['embedChapters'] is False
    assert page.state['remuxContainer'] == ''
    assert page.state['sponsorblockMark'] is False

    from PySide6.QtTest import QSignalSpy, QTest
    clicks = QSignalSpy(header.clicked)
    quick_window.root.resize(1200, 1000)
    run_frames(qapp, 160)
    click_item(quick_window, header)
    run_frames(qapp, 220)
    assert clicks.count() == 1
    assert page.state['advancedExpanded'] is True
    assert panel.isVisible()
    for name in ('embedThumbnail', 'embedMetadata', 'embedChapters'):
        assert find_item(quick_window, name).property('checked') is False
    assert find_item(quick_window, 'remuxContainer').property('currentIndex') == 0
    header.forceActiveFocus()
    assert header.property('activeFocus') is True

    page.setAdvancedToggle('clipEnabled', True)
    run_frames(qapp, 220)
    assert find_item(quick_window, 'clipStart').isVisible()
    header.forceActiveFocus()
    QTest.keyClick(quick_window.root, Qt.Key_Space)
    run_frames(qapp, 220)
    assert page.state['advancedExpanded'] is False
    assert not panel.isVisible()

@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_theme_palette_and_selection_contrast(quick_window, qapp, mode):
    from test_typography import _contrast_ratio
    quick_window.theme.set_mode(mode)
    palette = qapp.palette()
    assert (palette.color(QPalette.Window).lightness() < 80) == (mode == 'dark')
    assert _contrast_ratio(palette.color(QPalette.Highlight), palette.color(QPalette.HighlightedText)) >= 4.5

def test_error_dialog_copies_prebuilt_redacted_report(quick_window):
    dialog = ErrorSession(AppError('x','用户说明','技术详情'), 'safe report', quick_window)
    dialog.copyReport()
    assert QGuiApplication.clipboard().text() == 'safe report'


def test_actionable_error_dialog_localizes_actions_and_invokes_real_callback(quick_window):
    from yt_downloader.services.error_actions import error_presentation

    assert error_presentation('COOKIE_REQUIRED')[2] == ('OPEN_COOKIE_MANAGER', 'REPARSE')
    assert error_presentation('AUTH_REQUIRED')[2] == ('OPEN_COOKIE_MANAGER', 'REPARSE')
    assert error_presentation('format_unavailable')[2] == ('REPARSE',)
    assert error_presentation('NETWORK_ERROR')[2] == ('RETRY',)
    assert error_presentation('BROWSER_PROFILE_LOCKED')[2] == ('RETRY', 'OPEN_COOKIE_MANAGER')
    assert error_presentation('TEMPORARY_EXTRACTOR_ERROR')[2] == ('RETRY', 'CHECK_APP_UPDATE')
    assert 'OPEN_COOKIE_MANAGER' not in error_presentation('forbidden')[2]

    called = []
    error = AppError('COOKIE_REQUIRED', 'legacy body', 'raw technical detail',
                     title_message_id='error.cookie_required.title',
                     body_message_id='error.cookie_required.body',
                     recommended_actions=('OPEN_COOKIE_MANAGER', 'REPARSE'))
    dialog = ErrorSession(error, 'safe report', quick_window,
                          actions=error.recommended_actions,
                          action_callbacks={'OPEN_COOKIE_MANAGER': lambda: called.append('cookie')})
    dialog.show()
    quick_window.i18n.setLanguage('en-US')
    assert dialog.state['title'] == 'Cookie required'
    assert dialog.state['message'].startswith('This content requires a signed-in session')
    assert [item['label'] for item in dialog.state['errorActions']] == ['Manage cookies', 'Reparse']
    dialog.runAction('OPEN_COOKIE_MANAGER')
    assert called == ['cookie']
    assert not dialog.state['open']


def test_error_action_callbacks_open_cookie_reparse_and_check_app_update(quick_window, qtbot):
    from types import SimpleNamespace
    from yt_downloader.app import AppController
    from yt_downloader.core.errors import ErrorContext
    from yt_downloader.services.error_actions import error_presentation

    controller = object.__new__(AppController)
    controller.window = quick_window
    update_calls = []
    controller.updates = SimpleNamespace(check=lambda *, manual: update_calls.append(manual))

    cookie_error = AppError('COOKIE_REQUIRED', 'need auth', 'raw',
                            ErrorContext(url='https://site.example/member'),
                            *error_presentation('COOKIE_REQUIRED')[:2],
                            error_presentation('COOKIE_REQUIRED')[2])
    callbacks = controller._error_action_callbacks(cookie_error)
    callbacks['OPEN_COOKIE_MANAGER']()
    assert quick_window.state['page'] == 3

    with qtbot.waitSignal(quick_window.download_page.parse_requested) as parsed:
        controller._reparse_error_url(cookie_error.context.url)
    assert parsed.args == ['https://site.example/member']

    extractor_error = AppError('TEMPORARY_EXTRACTOR_ERROR', 'temporary', 'raw',
                               ErrorContext(url='https://site.example/video'),
                               *error_presentation('TEMPORARY_EXTRACTOR_ERROR')[:2],
                               error_presentation('TEMPORARY_EXTRACTOR_ERROR')[2])
    callbacks = controller._error_action_callbacks(extractor_error)
    callbacks['CHECK_APP_UPDATE']()
    assert quick_window.state['page'] == 4
    assert update_calls == [True]

def test_task_card_enters_cancelling_immediately(quick_window, tmp_path):
    page = quick_window.download_page
    request = _request(tmp_path)
    page.add_task(request)
    page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 31, 31, 100, 5000, 7))
    page.cancel_task(request.task_id)
    card = page.cards[request.task_id]
    assert card.values['statusText'] == '正在取消…'
    assert card.values['percent'] == 31
    assert not card.values['cancelEnabled']
    assert card.values['speed'] == '—' and card.values['eta'] == '剩余 —'

def test_task_remove_uses_stable_id_and_page_lifecycle(quick_window, tmp_path, qtbot):
    page = quick_window.download_page
    request = _request(tmp_path)
    page.add_task(request)
    with qtbot.waitSignal(page.remove_requested) as signal:
        page.taskAction(request.task_id, 'remove')
    assert signal.args == [request.task_id]
    page.remove_task(request.task_id)
    assert request.task_id not in page.cards
    assert page.tasks.count == 0

def test_cancel_cleanup_warning_offers_output_folder(quick_window, tmp_path, qtbot):
    page = quick_window.download_page
    request = _request(tmp_path); page.add_task(request)
    report = CancellationCleanupReport(task_id=request.task_id, output_directory=str(tmp_path), failed_paths=(str(tmp_path/'owned'),), errors=('locked',))
    page.fail_task(request.task_id, TaskStatus.CANCELLED, report)
    card = page.cards[request.task_id]
    assert '未能清理' in card.values['warningMessages'][0]
    assert card.values['statusKey'] == 'task.status.cancelled'
    with qtbot.waitSignal(page.open_folder_requested) as signal:
        page.taskAction(request.task_id, 'folder')
    assert signal.args == [str(tmp_path)]

def test_new_metadata_clears_previous_thumbnail_and_rejects_late_image(quick_window, tmp_path):
    from scripts.verify_quick_ui import sample_video
    page = quick_window.download_page
    source = sample_video()
    page.show_video(source)
    assert page.state['thumbnail']
    page.show_video(replace(source, video_id='second', thumbnail_bytes=None))
    assert page.state['thumbnail'] == ''
    assert not page.set_thumbnail(source.video_id, source.thumbnail_bytes)
    assert page.state['thumbnail'] == ''

def test_video_multilingual_wrapping_at_minimum_window(quick_window, qapp, tmp_path):
    quick_window.root.resize(500, 560)
    quick_window.download_page.show_video(replace(_request(tmp_path).video, title='桜のテスト動画 中文 한국어 '+ 'Long title '*20))
    run_frames(qapp, 100)
    title = find_item(quick_window, 'videoTitle')
    assert title.height() >= title.property('implicitHeight')
    assert title.property('font').pointSizeF() == 11.25
    assert title.width() > 0

def test_starting_next_task_retires_older_terminal_cards(quick_window, tmp_path):
    page = quick_window.download_page
    first = replace(_request(tmp_path), task_id='first')
    second = replace(first, task_id='second')
    page.add_task(first); page.add_task(second)
    page.complete_task(DownloadResult('first',tmp_path/'first.mp4',10,'now'))
    assert set(page.cards) == {'first','second'}
    page.task_started('second')
    assert set(page.cards) == {'second'}
    assert page.tasks.get(0)['id'] == 'second'


def test_completed_subtitle_warning_retranslates_without_translating_media_data(quick_window, qapp, tmp_path):
    from conftest import run_frames, find_item

    page = quick_window.download_page
    request = replace(_request(tmp_path), task_id='warning-i18n')
    page.add_task(request)
    page.complete_task(DownloadResult(
        request.task_id, tmp_path / 'done.mp4', 10, 'now',
        warnings=('字幕嵌入失败；媒体已保留，字幕另存为独立文件。',),
    ))
    quick_window.i18n.setLanguage('es-ES')
    run_frames(qapp)

    status = find_item(quick_window, 'taskStatus-warning-i18n')
    assert 'subtítulos' in status.property('text')
    assert 'embedded' not in status.property('text')

def test_download_selection_maps_to_original_domain_option(quick_window, tmp_path, qtbot):
    page = quick_window.download_page
    video = _request(tmp_path).video
    page.show_video(video)
    page.set_retry_defaults('chosen.name', str(tmp_path/'chosen'))
    with qtbot.waitSignal(page.download_requested) as signal:
        page.requestDownload()
    assert signal.args == [video, video.formats[page.state['formatIndex']], 'chosen.name', str(tmp_path/'chosen')]
    assert signal.args[1] is video.formats[page.state['formatIndex']]


def test_task_card_pause_resume_and_cancel_have_real_button_states(quick_window, tmp_path, qtbot):
    from conftest import find_item
    from yt_downloader.core.models import DownloadProgress, TaskStatus
    page = quick_window.download_page
    request = _request(tmp_path)
    page.add_task(request)
    page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 25, 1, 4))
    qtbot.waitUntil(lambda: find_item(quick_window, 'taskPause-' + request.task_id).isVisible(), timeout=2000)
    pause = find_item(quick_window, 'taskPause-' + request.task_id)
    cancel = find_item(quick_window, 'taskCancel-' + request.task_id)
    assert pause.property('appearance') == 'normal' and cancel.property('appearance') == 'normal'
    assert find_item(quick_window, 'taskStatus-' + request.task_id).property('text') == '正在下载视频'
    assert pause.property('text') == '暂停'
    assert cancel.property('text') == '取消'
    assert pause.isEnabled()
    with qtbot.waitSignal(page.pause_requested):
        page.taskAction(request.task_id, 'pause')
    page.paused_task(request.task_id)
    assert page.cards[request.task_id].values['resumeEnabled']
    assert find_item(quick_window, 'taskStatus-' + request.task_id).property('text') == '已暂停'
    assert pause.property('text') == '继续'
    with qtbot.waitSignal(page.resume_requested):
        page.taskAction(request.task_id, 'resume')
    page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 26, 1, 4))
    assert pause.property('text') == '暂停'
    page.update_task(DownloadProgress(request.task_id, TaskStatus.MERGING))
    assert not page.cards[request.task_id].values['pauseEnabled']

def test_settings_auto_save_after_text_edit_and_show_saved_status(quick_window, qtbot, tmp_path):
    page = quick_window.settings_page
    with qtbot.waitSignal(page.save_requested, timeout=1500) as signal:
        page.edit('download_directory', str(tmp_path/'新的目录'))
    saved = signal.args[0]
    assert saved.schema_version == 7
    assert saved.download_directory == str(tmp_path/'新的目录')
    assert page.state['saveText'] == '正在保存…'
    page.mark_saved(saved)
    assert page.state['saveText'] == '已保存'

def test_saved_directory_does_not_override_manual_choice(quick_window, tmp_path):
    page = quick_window.download_page; source = _request(tmp_path).video
    page.show_video(source); page.set_default_directory('second')
    assert page.state['directory'] == 'second'
    page.setField('directory', 'manual'); page.set_default_directory('third')
    assert page.state['directory'] == 'manual'
    page.show_video(replace(source, video_id='next'))
    assert page.state['directory'] == 'third'

def test_network_settings_round_trip_through_auto_save(quick_window, qtbot):
    page = quick_window.settings_page
    page.edit('custom_proxy_url','http://127.0.0.1:8080')
    page.edit('concurrent_fragments',4)
    with qtbot.waitSignal(page.save_requested) as signal:
        page.edit('proxy_mode','custom')
    assert signal.args[0].proxy_mode == 'custom'
    assert signal.args[0].custom_proxy_url == 'http://127.0.0.1:8080'
    assert signal.args[0].concurrent_fragments == 4

def test_default_profile_is_auto_saved(quick_window, qtbot):
    page = quick_window.settings_page
    with qtbot.waitSignal(page.save_requested) as signal:
        page.setDefaultProfile('best')
    assert signal.args[0].default_download_profile_id == 'best'
    assert signal.args[0].default_quality == 'highest'


def test_custom_profile_create_edit_delete_and_default_selection(quick_window, qtbot):
    page = quick_window.settings_page
    page.newProfile()
    assert page.state['profileDraftQuality'] == 'recommended'
    assert page.state['profileDraftCodec'] == 'auto'
    page.editProfileField('name', '动漫收藏')
    page.editProfileField('quality_tier', '1080p')
    page.editProfileField('subtitle_enabled', True)
    with qtbot.waitSignal(page.save_requested, timeout=1500):
        page.saveProfile()

    profile = page.current_settings().custom_download_profiles[0]
    assert profile.name == '动漫收藏'
    assert profile.quality_tier == '1080p'
    assert profile.subtitle_enabled
    assert page.state['defaultProfileId'] == 'auto'

    with qtbot.waitSignal(page.save_requested, timeout=1500):
        page.setDefaultProfile(profile.id)
    assert page.current_settings().default_download_profile_id == profile.id

    page.editProfile(profile.id)
    page.editProfileField('quality_tier', '2160p')
    with qtbot.waitSignal(page.save_requested, timeout=1500):
        page.saveProfile()
    assert page.current_settings().default_profile.quality_tier == '2160p'

    with qtbot.waitSignal(page.save_requested, timeout=1500):
        page.deleteProfile(profile.id)
    assert page.current_settings().default_download_profile_id == 'auto'
    assert page.current_settings().custom_download_profiles == ()


def test_profile_initializes_each_new_task_without_mutating_default(quick_window, tmp_path):
    page = quick_window.download_page
    request = _request(tmp_path)
    source = request.video
    from yt_downloader.core.formats import normalize_formats
    formats = [
        {'format_id': f'{codec}-{quality}', 'ext': 'mp4',
         'width': width, 'height': height, 'fps': fps, 'quality': quality,
         'vcodec': codec_value, 'acodec': 'none'}
        for quality, width, height, fps, codecs in (
            (120, 3360, 1890, 59.94, (('av1', 'av01.0.12M.08'),)),
            (116, 3555, 2000, 60.0, (('avc', 'avc1.640028'), ('av1', 'av01.0.08M.08'), ('hevc', 'hvc1.1.6.L120'))),
            (112, 1576, 886, 30.0, (('avc', 'avc1.640028'),)),
            (80, 1576, 886, 30.0, (('avc', 'avc1.640028'), ('av1', 'av01.0.08M.08'))),
            (74, 1280, 590, 59.94, (('avc', 'avc1.640028'),)),
            (64, 1280, 590, 30.0, (('avc', 'avc1.64001F'),)),
            (32, 702, 394, 30.0, (('avc', 'avc1.64001F'),)),
            (16, 524, 294, 30.0, (('avc', 'avc1.64001E'),)),
            (6, 426, 240, 30.0, (('avc', 'avc1.640015'),)),
        )
        for codec, codec_value in codecs
    ]
    video = replace(source, extractor_key='BiliBili', formats=tuple(normalize_formats(formats, extractor_key='BiliBili')))
    profile = DownloadProfile('p-high', '最高画质', quality_tier='highest', codec_preference='av1')

    page.show_video(video, profile=profile)
    assert page.state['formatIndex'] == 0
    assert page.state['formats'] == [
        '2160p 4K 60 FPS', '1080p 60 FPS', '1080p 高码率', '1080p',
        '720p 60 FPS', '720p', '480p', '360p', '240p',
    ]
    assert page.available_formats[page.state['formatIndex']].video_format_id == 'av1-120'
    assert page.state['qualityAuto'] is False
    page.selectFormat(1)  # Current-task override.
    assert page.state['formatIndex'] == 1
    assert profile.quality_tier == 'highest'

    page.show_video(replace(video, video_id='next'), profile=profile)
    assert page.state['formatIndex'] == 0
    assert page.state['mediaMode'] == 'video_audio'

def test_network_test_is_separate_from_save(quick_window, qtbot):
    page = quick_window.settings_page; saves = []
    page.save_requested.connect(saves.append)
    with qtbot.waitSignal(page.network_test_requested) as signal:
        page.testNetwork()
    assert signal.args == [page.state['proxy_mode'], '']
    assert page.state['networkBusy']
    page.set_network_test_result(True,'连接成功')
    assert not page.state['networkBusy']
    assert page.state['networkText'] == '连接成功'
    assert saves == []


def test_input_method_preedit_commits_multilingual_filename(quick_window,qapp,tmp_path):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QInputMethodEvent
    quick_window.download_page.show_video(_request(tmp_path).video)
    field=find_item(quick_window,'filenameInput')
    field.forceActiveFocus()
    field.setProperty('text','')
    preedit=QInputMethodEvent('zhongwen',[])
    QCoreApplication.sendEvent(quick_window.root,preedit)
    assert field.property('text') == ''
    commit=QInputMethodEvent()
    commit.setCommitString('中文 桜 한국어 🎬')
    QCoreApplication.sendEvent(quick_window.root,commit)
    assert quick_window.download_page.state['filename'] == '中文 桜 한국어 🎬'


def test_accessibility_value_updates_reach_the_presenter(quick_window,qapp,tmp_path,qtbot):
    page=quick_window.download_page
    find_item(quick_window,'urlInput').setProperty('text','invalid')
    with qtbot.waitSignal(page.parse_requested) as signal:
        page.requestParse()
    assert signal.args == ['invalid']
    page.show_video(_request(tmp_path).video)
    find_item(quick_window,'directoryInput').setProperty('text','D:/Accessible')
    page.set_default_directory('D:/NewDefault')
    assert page.state['directory']=='D:/Accessible'
    page.show_video(_request(tmp_path).video)
    assert page.state['directory']=='D:/NewDefault'

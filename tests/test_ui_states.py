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
    assert button.property('text') == '正在取消…'
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
    assert '未能清理' in page.cards[request.task_id].values['statusText']
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
    assert pause.isEnabled()
    with qtbot.waitSignal(page.pause_requested):
        page.taskAction(request.task_id, 'pause')
    page.paused_task(request.task_id)
    assert page.cards[request.task_id].values['resumeEnabled']
    with qtbot.waitSignal(page.resume_requested):
        page.taskAction(request.task_id, 'resume')
    page.update_task(DownloadProgress(request.task_id, TaskStatus.MERGING))
    assert not page.cards[request.task_id].values['pauseEnabled']

def test_settings_auto_save_after_text_edit_and_show_saved_status(quick_window, qtbot, tmp_path):
    page = quick_window.settings_page
    with qtbot.waitSignal(page.save_requested, timeout=1500) as signal:
        page.edit('download_directory', str(tmp_path/'新的目录'))
    saved = signal.args[0]
    assert saved.schema_version == 6
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

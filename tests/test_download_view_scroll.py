"""Viewport behavior through the actual Qt Quick download view."""
from dataclasses import replace
from types import SimpleNamespace

from PySide6.QtCore import QPointF

from yt_downloader.app import AppController
from yt_downloader.workers.request_gate import LatestRequestGate

from conftest import click_item, find_item, run_frames
from scripts.verify_quick_ui import sample_video


def scene_y(item):
    return item.mapToScene(QPointF(0, 0)).y()


def scroll_to(window, item, offset=100):
    view = find_item(window, 'taskList')
    origin = view.property('originY')
    maximum = origin + max(0, view.property('contentHeight') - view.height())
    desired = view.property('contentY') + scene_y(item) - scene_y(view) - offset
    view.setProperty('contentY', max(origin, min(maximum, desired)))


def test_local_expansion_keeps_header_visual_anchor(quick_window, qapp):
    page = quick_window.download_page
    page.show_video(sample_video())
    run_frames(qapp)
    header = find_item(quick_window, 'advancedOptionsToggle')
    scroll_to(quick_window, header)
    run_frames(qapp, 50)
    before = scene_y(header)
    click_item(quick_window, header)
    run_frames(qapp)
    assert page.state['advancedExpanded']
    assert abs(scene_y(header) - before) < 2
    click_item(quick_window, header)
    run_frames(qapp)
    assert not page.state['advancedExpanded']
    assert abs(scene_y(header) - before) < 2


def test_clip_and_postprocess_changes_preserve_scroll(quick_window, qapp):
    page = quick_window.download_page
    page.show_video(sample_video())
    page.setAdvancedToggle('advancedExpanded', True)
    run_frames(qapp)
    toggle = find_item(quick_window, 'clipEnabled')
    scroll_to(quick_window, toggle)
    run_frames(qapp, 50)
    before = scene_y(toggle)
    for enabled in (True, False):
        page.setAdvancedToggle('clipEnabled', enabled)
        for _ in range(14):
            run_frames(qapp, 20)
            assert abs(scene_y(toggle) - before) < 2
    for name in ('embedThumbnail', 'embedMetadata', 'embedChapters', 'sponsorblockMark'):
        page.setAdvancedToggle(name, True)
        run_frames(qapp, 50)
        assert abs(scene_y(toggle) - before) < 2
    page.setAdvancedField('remuxContainer', 'mkv')
    page.selectFormat(0)
    page.setAdvancedField('clipStart', '03:15')
    run_frames(qapp)
    assert abs(scene_y(toggle) - before) < 2


def test_collapse_at_content_end_keeps_view_in_bounds(quick_window, qapp):
    page = quick_window.download_page
    page.show_video(sample_video())
    page.setAdvancedToggle('advancedExpanded', True)
    run_frames(qapp)
    scroll_to(quick_window, find_item(quick_window, 'downloadButton'))
    page.setAdvancedToggle('advancedExpanded', False)
    run_frames(qapp)
    view = find_item(quick_window, 'taskList')
    offset = view.property('contentY') - view.property('originY')
    assert 0 <= offset <= max(0, view.property('contentHeight') - view.height()) + 1


def test_successful_result_positions_after_layout_once(quick_window, qapp):
    page = quick_window.download_page
    source = sample_video()
    page.show_video(source)
    run_frames(qapp)
    view = find_item(quick_window, 'taskList')
    scroll_to(quick_window, find_item(quick_window, 'advancedOptionsToggle'))
    run_frames(qapp, 50)
    controller = AppController.__new__(AppController)
    controller.window = quick_window
    controller.settings = SimpleNamespace(default_profile=quick_window.settings_page.current_settings().default_profile)
    controller._pending_retry = None
    controller._metadata_gate = LatestRequestGate()
    controller._start_thumbnail = lambda video: None
    stale = controller._metadata_gate.begin('old')
    token = controller._metadata_gate.begin('next')
    page.set_loading(True)
    before = scene_y(find_item(quick_window, 'videoPanel')) - scene_y(view)
    run_frames(qapp)
    assert abs(scene_y(find_item(quick_window, 'videoPanel')) - scene_y(view) - before) < 2
    controller._metadata_result(stale, replace(source, video_id='stale'))
    assert page.state['title'] == source.title
    controller._metadata_result(token, replace(source, video_id='next', title='New media'))
    page.set_loading(False)
    run_frames(qapp)
    panel = find_item(quick_window, 'videoPanel')
    assert abs(scene_y(panel) - scene_y(view)) < 2
    scroll_to(quick_window, find_item(quick_window, 'advancedOptionsToggle'))
    run_frames(qapp, 50)
    before = scene_y(panel)
    page.set_thumbnail('next', source.thumbnail_bytes)
    page.update(cookieAuthStatus='Updated', technical='Updated format summary')
    run_frames(qapp)
    assert abs(scene_y(panel) - before) < 2

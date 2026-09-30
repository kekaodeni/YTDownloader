"""Viewport behavior through the actual Qt Quick download view."""
from dataclasses import replace
from types import SimpleNamespace

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtTest import QTest
import pytest

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


@pytest.mark.parametrize('field', ['advancedExpanded', 'clipEnabled'])
@pytest.mark.parametrize('extractor', ['Youtube', 'BiliBili'])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_every_rendered_toggle_frame_keeps_card_and_anchor(quick_window, qapp, field, extractor, theme):
    page = quick_window.download_page
    quick_window.theme.set_mode(theme)
    page.show_video(replace(sample_video(), extractor_key=extractor))
    if field == 'clipEnabled':
        page.setAdvancedToggle('advancedExpanded', True)
    run_frames(qapp)
    item = find_item(quick_window, 'advancedOptionsToggle' if field == 'advancedExpanded' else 'clipEnabled')
    scroll_to(quick_window, item)
    run_frames(qapp, 50)
    baseline = scene_y(item)
    panel = find_item(quick_window, 'videoPanel')
    initial = quick_window.grab()
    sidebar_width = round(190 * quick_window.root.devicePixelRatio())
    sidebar = initial.copy(0, 0, sidebar_width, initial.height())
    controls = [find_item(quick_window, name) for name in ('advancedOptionsPanel','clipStart','clipEnd')]
    observations = []
    def capture():
        # grabWindow renders a real scene-graph frame, rather than only checking
        # the endpoint after a 280ms animation has finished.
        picture = quick_window.grab()
        observations.append((scene_y(item), panel.isVisible(), panel.opacity(), picture.isNull(),
                             picture.copy(0, 0, sidebar_width, picture.height()) == sidebar))
    timer = QTimer()
    timer.timeout.connect(capture)
    timer.start(5)
    try:
        for enabled in (True, False, True, False):
            if field == 'advancedExpanded':
                click_item(quick_window, item)
            else:
                # UiSettingToggle's switch is at the trailing edge of its row.
                point = item.mapToScene(QPointF(item.width() - 31, item.height() / 2)).toPoint()
                QTest.mouseClick(quick_window.root, Qt.LeftButton, Qt.NoModifier, point)
            assert page.state[field] == enabled
            assert not controls[1].hasActiveFocus() and not controls[2].hasActiveFocus()
            run_frames(qapp, 240)
    finally:
        timer.stop()
    assert observations
    assert controls == [find_item(quick_window, name) for name in ('advancedOptionsPanel','clipStart','clipEnd')]
    assert all(abs(y - baseline) < 2 and visible and opacity == 1 and not blank and stable_sidebar
               for y, visible, opacity, blank, stable_sidebar in observations), observations


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

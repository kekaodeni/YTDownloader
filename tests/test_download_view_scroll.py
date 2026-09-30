"""Viewport behavior through the actual Qt Quick download view."""
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path

from PySide6.QtCore import QPointF, QTimer, Qt, QMetaObject, Q_ARG
from PySide6.QtTest import QTest
import pytest

from yt_downloader.app import AppController
from yt_downloader.workers.request_gate import LatestRequestGate

from conftest import click_item, find_item, run_frames
from scripts.verify_quick_ui import sample_video
from yt_downloader.core.models import DownloadRequest


def add_anchor_test_tasks(page):
    video = sample_video()
    for index in range(3):
        page.add_task(DownloadRequest(f'anchor-{index}', video, video.formats[0], Path(page.state['directory']), 'anchor'))


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
    add_anchor_test_tasks(page)
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
@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('enabled', [False, True])
def test_bottom_mutation_preserves_bottom_in_every_rendered_frame(quick_window, qapp, field, theme, enabled):
    page = quick_window.download_page
    quick_window.theme.set_mode(theme)
    page.show_video(sample_video())
    add_anchor_test_tasks(page)
    page.setAdvancedToggle('advancedExpanded', field == 'clipEnabled' or not enabled)
    page.setAdvancedToggle('clipEnabled', not enabled if field == 'clipEnabled' else True)
    run_frames(qapp)
    view = find_item(quick_window, 'taskList')
    view.setProperty('contentY', view.property('originY') + view.property('contentHeight') - view.height())
    run_frames(qapp, 60)
    observations = []
    timer = QTimer()
    def capture():
        assert not quick_window.grab().isNull()
        gap = view.property('contentHeight') - (view.property('contentY') - view.property('originY')) - view.height()
        observations.append(gap)
    timer.timeout.connect(capture)
    timer.start(5)
    try:
        item = find_item(quick_window, 'advancedOptionsToggle' if field == 'advancedExpanded' else 'clipEnabled')
        if field == 'advancedExpanded':
            QMetaObject.invokeMethod(item, 'clicked', Qt.DirectConnection)
        else:
            QMetaObject.invokeMethod(item, 'changed', Qt.DirectConnection, Q_ARG(bool, enabled))
        assert page.state[field] == enabled
        run_frames(qapp, 300)
    finally:
        timer.stop()
    assert observations
    assert all(abs(gap) < 2 or view.property('contentHeight') <= view.height() for gap in observations), observations
    assert not find_item(quick_window, 'viewportAnchor').property('mutating')
    view.setProperty('contentY', view.property('originY'))
    run_frames(qapp, 60)
    assert abs(view.property('contentY') - view.property('originY')) < 1


@pytest.mark.parametrize('offset', [120, 350])
def test_removing_last_task_preserves_or_smoothly_follows_disclosure(quick_window, qapp, offset):
    import time
    page = quick_window.download_page
    video = sample_video()
    page.show_video(video)
    page.setAdvancedToggle('advancedExpanded', True)
    page.add_task(DownloadRequest('last', video, video.formats[0], Path(page.state['directory']), 'last'))
    run_frames(qapp)
    item = find_item(quick_window, 'advancedOptionsToggle')
    scroll_to(quick_window, item, offset)
    run_frames(qapp, 80)
    samples = [(time.perf_counter(), scene_y(item))]
    timer = QTimer()
    def capture():
        quick_window.grab()
        samples.append((time.perf_counter(), scene_y(item)))
    timer.timeout.connect(capture)
    timer.start(8)
    try:
        page.remove_task('last')
        run_frames(qapp, 550)
    finally:
        timer.stop()
    distance = abs(samples[-1][1] - samples[0][1])
    if distance > 2:
        assert len({round(y, 1) for _, y in samples}) > 5
        assert all(abs(y2-y1) <= 3*distance/.170*(t2-t1+.017)+5
                   for (t1,y1),(t2,y2) in zip(samples,samples[1:])), samples
    else:
        assert all(abs(y-samples[0][1]) < 2 for _,y in samples)
    helper = find_item(quick_window, 'viewportAnchor')
    assert not helper.property('mutating'), {key: helper.property(key) for key in (
        'boundaryReserve', 'removalAnimating', 'removingLastTask', 'finishingBoundary',
        'renderedMutationHeader', 'renderedMutationContent', 'headerHeight', 'offset')}


@pytest.mark.parametrize('field', ['advancedExpanded', 'clipEnabled'])
@pytest.mark.parametrize('extractor', ['Youtube', 'BiliBili'])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_every_rendered_toggle_frame_keeps_card_and_anchor(quick_window, qapp, field, extractor, theme):
    page = quick_window.download_page
    quick_window.theme.set_mode(theme)
    page.show_video(replace(sample_video(), extractor_key=extractor))
    add_anchor_test_tasks(page)
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
            # Bring the action back into view if preserving the bottom moved
            # it above the viewport; record the anchor for this mutation.
            if scene_y(item) < scene_y(find_item(quick_window, 'taskList')):
                scroll_to(quick_window, item)
                run_frames(qapp, 50)
            view = find_item(quick_window, 'taskList')
            maximum = max(0, view.property('contentHeight') - view.height())
            bottom_distance = maximum - (view.property('contentY') - view.property('originY'))
            bottom = maximum > 0 and bottom_distance <= 6
            baseline = scene_y(item)
            observations.clear()
            if field == 'advancedExpanded':
                click_item(quick_window, item)
            else:
                # UiSettingToggle's switch is at the trailing edge of its row.
                point = item.mapToScene(QPointF(item.width() - 31, item.height() / 2)).toPoint()
                QTest.mouseClick(quick_window.root, Qt.LeftButton, Qt.NoModifier, point)
            assert page.state[field] == enabled
            assert not controls[1].hasActiveFocus() and not controls[2].hasActiveFocus()
            run_frames(qapp, 240)
            assert observations
            assert all(visible and opacity == 1 and not blank and stable_sidebar
                       for y, visible, opacity, blank, stable_sidebar in observations), observations
            if bottom:
                assert abs(view.property('contentHeight') - (view.property('contentY') - view.property('originY')) - view.height() - bottom_distance) < 2
            else:
                assert all(abs(y - baseline) < 2 for y, *_ in observations), observations
    finally:
        timer.stop()
    assert observations
    assert controls == [find_item(quick_window, name) for name in ('advancedOptionsPanel','clipStart','clipEnd')]
    assert all(visible and opacity == 1 and not blank and stable_sidebar
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


@pytest.mark.parametrize('field', ['advancedExpanded', 'clipEnabled'])
@pytest.mark.parametrize('after_removal', [False, True])
@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('anchor_offset', [20, 150])
def test_empty_task_disclosure_has_no_instant_jump(quick_window, qapp, field, after_removal, theme, anchor_offset):
    page = quick_window.download_page
    quick_window.theme.set_mode(theme)
    page.show_video(sample_video())
    if after_removal:
        video = sample_video()
        page.add_task(DownloadRequest('last', video, video.formats[0], Path(page.state['directory']), 'last'))
    page.setAdvancedToggle('advancedExpanded', True)
    page.setAdvancedToggle('clipEnabled', True)
    run_frames(qapp)
    item = find_item(quick_window, 'advancedOptionsToggle' if field == 'advancedExpanded' else 'clipEnabled')
    scroll_to(quick_window, item, anchor_offset)
    run_frames(qapp, 60)
    view = find_item(quick_window, 'taskList')
    if after_removal:
        page.remove_task('last')
        run_frames(qapp, 500)
        assert view.property('count') == 0
        scroll_to(quick_window, item, anchor_offset)
        run_frames(qapp, 80)
    samples = []
    def capture():
        import time
        quick_window.grab()
        samples.append(dict(at=time.perf_counter(), y=scene_y(item), height=view.property('contentHeight'),
                            contentY=view.property('contentY'), origin=view.property('originY'),
                            maximum=max(0, view.property('contentHeight') - view.height())))
    capture()
    timer = QTimer()
    timer.timeout.connect(capture)
    timer.start(8)
    try:
        click_item(quick_window, item) if field == 'advancedExpanded' else QTest.mouseClick(
            quick_window.root, Qt.LeftButton, Qt.NoModifier,
            item.mapToScene(QPointF(item.width() - 31, item.height() / 2)).toPoint())
        run_frames(qapp, 500)
    finally:
        timer.stop()
    assert not page.state[field]
    import json
    Path('artifacts/motion').mkdir(parents=True, exist_ok=True)
    Path(f'artifacts/motion/empty-{field}.json').write_text(json.dumps(samples), encoding='utf-8')
    distance = abs(samples[-1]['y'] - samples[0]['y'])
    old_offset = samples[0]['contentY'] - samples[0]['origin']
    final_offset = min(old_offset, samples[-1]['maximum'])
    expected_y = samples[0]['y'] + old_offset - final_offset
    assert abs(samples[-1]['y'] - expected_y) < 2, samples
    if distance > 2:
        assert len({round(s['y'], 1) for s in samples}) > 5, samples
        # Account for skipped scene-graph frames: OutCubic's maximum initial
        # slope is 3 * distance / duration, rather than an arbitrary px/frame.
        assert all(abs(b['y'] - a['y']) <= 3 * distance / .170 * (b['at'] - a['at'] + .017) + 5
                   for a, b in zip(samples, samples[1:])), samples
    assert 0 <= view.property('contentY') - view.property('originY') <= max(0, view.property('contentHeight') - view.height()) + 1
    assert find_item(quick_window, 'viewportAnchor').property('boundaryReserve') == 0
    assert not find_item(quick_window, 'viewportAnchor').property('mutating')

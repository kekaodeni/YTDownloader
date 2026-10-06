"""Native Qt Quick events exercise the shared dropdown, including non-language use."""
import pytest
from PySide6.QtCore import QPointF, QTimer, QMetaObject, Q_ARG, Qt
from PySide6.QtTest import QTest
from conftest import find_item, click_item, run_frames
from test_quick_scroll import wheel
from test_language_selector import language_wheel
from yt_downloader.services.media_metadata import resolve_metadata


def prepare_dropdown(window, app, name):
    if name == 'collectionQualityCombo':
        window.download_page.show_video(resolve_metadata(dict(_type='playlist', extractor_key='Youtube',
            entries=[dict(id='new', title='New', url='https://youtu.be/new', ie_key='Youtube')]),
            'https://www.youtube.com/playlist?list=list'))
        window._select_page(0)
    elif name == 'formatCombo':
        import json
        from pathlib import Path
        raw = json.loads(Path('tests/fixtures/bilibili_embedded_replay.json').read_text('utf-8'))
        raw = dict(raw['entries'][0], _type='video')
        window.download_page.show_video(resolve_metadata(raw, 'https://www.bilibili.com/video/BV1TiGg6kErJ/'))
        window._select_page(0)
    else:
        window._select_page(3)
    run_frames(app)
    combo = find_item(window, name)
    click_item(window, combo)
    run_frames(app, 180)
    return combo, find_item(window, 'popup-' + name), find_item(window, 'options-' + name)


@pytest.mark.parametrize('name', ['collectionQualityCombo', 'formatCombo', 'languageCombo', 'themeCombo'])
@pytest.mark.parametrize('edge', ['top', 'bottom'])
@pytest.mark.parametrize('reduced', [False, True])
def test_shared_dropdown_boundary_behavior(quick_window, qapp, name, edge, reduced):
    quick_window.settings_page.setSetting('reduce_motion', reduced)
    combo, popup, view = prepare_dropdown(quick_window, qapp, name)
    bar = next(x for x in view.childItems() if x.inherits('QQuickScrollBar'))
    top = view.property('originY')
    bottom = top + max(0, view.property('contentHeight') - view.height())
    position = top if edge == 'top' else bottom
    view.setProperty('contentY', position)
    run_frames(qapp, 180)
    def geometry():
        return (popup.property('x'), popup.property('y'), popup.property('width'), popup.property('height'),
                bar.x(), bar.y(), bar.width(), bar.height(), bar.property('size'), bar.property('position'),
                combo.property('model'), combo.property('currentIndex'))
    baseline = geometry()
    observations, sent = [], []
    direction = 1 if edge == 'top' else -1
    inertia = []
    timer = QTimer()
    timer.timeout.connect(lambda: inertia.append(view.property('contentY')))
    timer.start(4)
    try:
        assert QMetaObject.invokeMethod(view, 'flick', Q_ARG(float, 0.), Q_ARG(float, direction*2200.))
        run_frames(qapp, 400)
    finally:
        timer.stop()
    assert all(top-.01 <= y <= bottom+.01 for y in inertia)
    def tick():
        if len(sent) < 20:
            before = view.property('elasticOffset')
            wheel(quick_window, view, angle=direction*120)
            sent.append((before, view.property('elasticOffset')))
        observations.append((view.property('contentY'), view.property('elasticOffset'), geometry()))
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(4)
    try:
        run_frames(qapp, 270)
    finally:
        timer.stop()
    assert len(sent) == 20
    assert all(before == after for before, after in sent)  # Events never assign/restart displacement.
    assert all(abs(y-position) < .01 and abs(offset) <= (0 if reduced else 4.01)
               and g == baseline for y, offset, g in observations)
    assert view.property('elasticOffset') == 0
    if not reduced:
        assert max(abs(o[1]) for o in observations) > 3
    assert QMetaObject.invokeMethod(view, 'flick', Q_ARG(float, 0.), Q_ARG(float, direction*2200.))
    run_frames(qapp, 300)
    assert view.property('contentY') == pytest.approx(position, abs=.01)
    assert abs(view.property('verticalOvershoot')) < .01
    if bottom > top:
        language_wheel(quick_window, view, pixels=-direction*24, native=True)
        run_frames(qapp, 180)
        assert top <= view.property('contentY') <= bottom
        assert abs(view.property('contentY') - position) > 0
    QTest.keyClick(quick_window.root, Qt.Key_Escape)

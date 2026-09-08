from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QWidget

from yt_downloader.ui.diagnostics import ReducedMotionPolicy, UIAnimationDiagnostics


def test_stall_percentiles_and_severity_thresholds(qapp):
    diagnostics = UIAnimationDiagnostics()
    for value in range(1, 101):
        diagnostics.record_stall(float(value) / 4)
    report = diagnostics.report()
    assert report['p95_ms'] == 23.75
    assert report['p99_ms'] == 24.75
    assert report['max_ms'] == 25.0
    assert report['serious_regressions'] == 0
    diagnostics.record_stall(101)
    assert diagnostics.report()['serious_regressions'] == 1


def test_diagnostics_counts_real_paint_and_layout_and_active_proxies(qapp, qtbot):
    diagnostics = UIAnimationDiagnostics()
    active = {'count': 2}
    diagnostics.register_active_provider(lambda: active['count'])
    diagnostics.start(qapp)
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.update()
    widget.layoutRequest = QEvent(QEvent.Type.LayoutRequest)
    qapp.sendEvent(widget, widget.layoutRequest)
    qapp.processEvents()
    report = diagnostics.report()
    diagnostics.stop()
    assert report['paint_events'] >= 1
    assert report['layout_requests'] >= 1
    assert report['active_visual_objects'] == 2


def test_reduced_motion_policy_emits_only_real_runtime_changes(qtbot):
    policy = ReducedMotionPolicy(False)
    values = []
    policy.changed.connect(values.append)
    policy.set_enabled(False)
    policy.set_enabled(True)
    policy.set_enabled(True)
    policy.set_enabled(False)
    assert values == [True, False]

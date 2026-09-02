from yt_downloader.core.models import DownloadProgress, TaskStatus
from yt_downloader.ui.widgets.progress_widget import ProgressWidget


def test_progress_bar_percent_and_speed_are_always_visible(qtbot) -> None:
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO))

    assert widget.progress_bar.isVisible()
    assert widget.percent_label.isVisible()
    assert widget.speed_label.isVisible()
    assert widget.percent_label.text() == "—%"
    assert widget.speed_label.text() == "—"


def test_cancelling_freezes_progress_and_clears_live_metrics(qtbot) -> None:
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.set_progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, 42, 42, 100, 2_000_000, 9))

    widget.set_progress(DownloadProgress("x", TaskStatus.CANCELLING))

    assert widget.status_label.text() == "正在取消…"
    assert (widget.progress_bar.minimum(), widget.progress_bar.maximum()) == (0, 100)
    assert widget.progress_bar.value() == 42
    assert widget.percent_label.text() == "42%"
    assert widget.speed_label.text() == "—"
    assert widget.eta_label.text() == "剩余 —"


def test_estimated_total_is_labeled_instead_of_presented_as_exact(qtbot) -> None:
    widget = ProgressWidget()
    qtbot.addWidget(widget)

    widget.set_progress(
        DownloadProgress(
            "x",
            TaskStatus.DOWNLOADING_VIDEO,
            20,
            50,
            250,
            1000,
            2,
            total_is_estimate=True,
        )
    )

    assert widget.size_label.text() == "50 B / 估算 250 B"


def test_unknown_total_keeps_downloaded_speed_and_eta_visible(qtbot) -> None:
    widget = ProgressWidget()
    qtbot.addWidget(widget)

    widget.set_progress(
        DownloadProgress(
            "x",
            TaskStatus.DOWNLOADING_VIDEO,
            percent=None,
            downloaded_bytes=512,
            total_bytes=None,
            speed=1024,
            eta=12,
        )
    )

    assert (widget.progress_bar.minimum(), widget.progress_bar.maximum()) == (0, 0)
    assert widget.percent_label.text() == "—%"
    assert widget.size_label.text() == "512 B / —"
    assert widget.speed_label.text() == "1.0 KB/s"
    assert widget.eta_label.text() == "剩余 00:12"


def test_progress_switches_from_unknown_to_determinate_without_reset(qtbot) -> None:
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.set_progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, None, 100, None, 50, None))

    widget.set_progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, 20, 200, 1000, 50, 16))

    assert (widget.progress_bar.minimum(), widget.progress_bar.maximum()) == (0, 100)
    assert widget.progress_bar.value() == 20
    assert widget.percent_label.text() == "20%"

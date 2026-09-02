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


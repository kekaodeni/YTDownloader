from types import SimpleNamespace

from yt_downloader.app import AppController
from yt_downloader.core.models import DownloadProgress, TaskStatus


def test_progress_persists_only_download_stage_changes(qapp):
    writes = []
    controller = object.__new__(AppController)
    controller.window = SimpleNamespace(download_page=SimpleNamespace(update_task=lambda _value: None))
    controller.history = SimpleNamespace(update_status=lambda task, status: writes.append((task, status)))
    controller._persisted_task_stages = {}
    for value in range(100):
        controller._progress(DownloadProgress('task', TaskStatus.DOWNLOADING_VIDEO, value))
    controller._progress(DownloadProgress('task', TaskStatus.DOWNLOADING_AUDIO, 50))
    controller._progress(DownloadProgress('task', TaskStatus.DOWNLOADING_AUDIO, 51))
    assert writes == [
        ('task', TaskStatus.DOWNLOADING_VIDEO),
        ('task', TaskStatus.DOWNLOADING_AUDIO),
    ]


def test_gui_dispatch_coalesces_same_stage_but_never_loses_stage_transition(qapp, qtbot):
    from yt_downloader.ui.progress_dispatch import ProgressEventCoalescer

    coalescer = ProgressEventCoalescer()
    values = []
    coalescer.dispatched.connect(values.append)
    for value in range(100):
        coalescer.push(DownloadProgress('task', TaskStatus.DOWNLOADING_VIDEO, value))
    coalescer.push(DownloadProgress('task', TaskStatus.DOWNLOADING_AUDIO, 10))
    assert [(value.status, value.percent) for value in values] == [
        (TaskStatus.DOWNLOADING_VIDEO, 0),
        (TaskStatus.DOWNLOADING_VIDEO, 99),
        (TaskStatus.DOWNLOADING_AUDIO, 10),
    ]

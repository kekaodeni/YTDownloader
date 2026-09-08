from dataclasses import replace

import pytest

from PySide6.QtCore import Qt

from test_download_service import _request
from test_history_repository import _record
from yt_downloader.app import AppController
from yt_downloader.core.errors import AppError
from yt_downloader.core.models import DownloadProgress, ParseState, TaskStatus
from yt_downloader.infrastructure.paths import AppPaths
from yt_downloader.ui.quick_download import TaskPresentation


@pytest.mark.parametrize("status", [TaskStatus.PENDING, TaskStatus.DOWNLOADING_VIDEO, TaskStatus.CANCELLING, TaskStatus.CANCELLED, TaskStatus.COMPLETED])
def test_retry_is_not_offered_for_non_failed_tasks(qtbot, tmp_path, status):
    card = TaskPresentation(_request(tmp_path))
    card.progress(DownloadProgress(card.request.task_id, status))
    assert not card.values['retry']


def test_failed_card_retry_reparses_without_auto_download(qapp, qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("YT_DOWNLOADER_VIDEOS_DIR", str(tmp_path / "default"))
    paths = AppPaths.discover(tmp_path / "app-data")
    paths.ensure()
    controller = AppController(qapp, paths)
    controller.window.show()
    page = controller.window.download_page
    request = replace(_request(tmp_path / "chosen"), filename_stem="chosen.name")
    record = replace(_record(tmp_path, request.task_id, TaskStatus.PENDING), url=request.video.url)
    controller.history.upsert(record)
    controller.queue.task_queued.emit(request)
    controller.queue.failed.emit(request.task_id, AppError("network", "网络连接中断。", "test"))
    for dialog in tuple(controller._dialogs):
        dialog.close()
    card = page.cards[request.task_id]
    assert card.values['retry']
    assert not card.values["cancel"]
    calls = []

    def start_process(token, url, config):
        calls.append((token, url))
        controller.metadata_process.state_changed.emit(ParseState.RUNNING)

    monkeypatch.setattr(controller.metadata_process, "start", start_process)
    page.taskAction(request.task_id, "retry")
    assert len(calls) == 1
    assert calls[0][1] == request.video.url
    assert page.state["url"] == request.video.url
    assert page.parse_state is ParseState.RUNNING
    assert page.state["busy"]
    page.taskAction(request.task_id, "retry")
    assert len(calls) == 1
    controller.metadata_process.result.emit(calls[0][0], request.video)
    controller.metadata_process.state_changed.emit(ParseState.SUCCEEDED)
    assert page.video == request.video
    assert page.state["filename"] == "chosen.name"
    assert page.state["directory"] == str(request.output_directory)
    assert page.video.formats[page.state["formatIndex"]].label == request.format.label
    assert not page.state["busy"]
    assert not controller.queue.is_busy
    assert controller.history.get(request.task_id).status is TaskStatus.FAILED
    assert len(controller.history.list_records()) == 1
    controller._shutdown_background_operations()
    controller.window.update(allowClose=True)
    controller.window.close()
    controller.window.dispose()

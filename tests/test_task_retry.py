from dataclasses import replace

import pytest

from PySide6.QtCore import Qt

from test_download_service import _request
from test_history_repository import _record
from yt_downloader.app import AppController
from yt_downloader.core.errors import AppError
from yt_downloader.core.models import DownloadProgress, ParseState, TaskStatus
from yt_downloader.infrastructure.paths import AppPaths
from yt_downloader.ui.widgets.task_card import DownloadTaskCard


@pytest.mark.parametrize("status", [TaskStatus.PENDING, TaskStatus.DOWNLOADING_VIDEO, TaskStatus.CANCELLING, TaskStatus.CANCELLED, TaskStatus.COMPLETED])
def test_retry_is_not_offered_for_non_failed_tasks(qtbot, tmp_path, status):
    card = DownloadTaskCard(_request(tmp_path))
    qtbot.addWidget(card)
    card.show()
    card.set_terminal_status(TaskStatus.FAILED)
    card.update_progress(DownloadProgress(card.request.task_id, status))
    assert not card.retry_button.isVisible()


def test_failed_card_retry_reparses_without_auto_download(qapp, qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("YT_DOWNLOADER_VIDEOS_DIR", str(tmp_path / "default"))
    paths = AppPaths.discover(tmp_path / "app-data")
    paths.ensure()
    controller = AppController(qapp, paths)
    qtbot.addWidget(controller.window)
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
    assert card.retry_button.isVisible()
    assert card.retry_button.text() == "重试"
    assert not card.cancel_button.isVisible()
    assert card.retry_button.accessibleName()
    assert card.retry_button.toolTip()
    calls = []

    def start_process(token, url, config):
        calls.append((token, url))
        controller.metadata_process.state_changed.emit(ParseState.RUNNING)

    monkeypatch.setattr(controller.metadata_process, "start", start_process)
    card.retry_button.setFocus()
    qtbot.keyClick(card.retry_button, Qt.Key.Key_Space)
    assert len(calls) == 1
    assert calls[0][1] == request.video.url
    assert page.url_input.text() == request.video.url
    assert page.parse_state is ParseState.RUNNING
    assert not card.retry_button.isEnabled()
    card.retry_button.click()
    assert len(calls) == 1
    controller.metadata_process.result.emit(calls[0][0], request.video)
    controller.metadata_process.state_changed.emit(ParseState.SUCCEEDED)
    assert page.video == request.video
    assert page.filename_input.text() == "chosen.name"
    assert page.directory_input.text() == str(request.output_directory)
    assert page.format_combo.currentData().label == request.format.label
    assert card.retry_button.isEnabled()
    assert not controller.queue.is_busy
    assert controller.history.get(request.task_id).status is TaskStatus.FAILED
    assert len(controller.history.list_records()) == 1
    controller._shutdown_background_operations()

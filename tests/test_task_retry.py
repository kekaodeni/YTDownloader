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


def test_failed_card_retry_reuses_task_without_reparsing(qapp, qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("YT_DOWNLOADER_VIDEOS_DIR", str(tmp_path / "default"))
    paths = AppPaths.discover(tmp_path / "app-data")
    paths.ensure()
    controller = AppController(qapp, paths)
    controller.window.show()
    page = controller.window.download_page
    request = replace(_request(tmp_path / "chosen"), filename_stem="chosen.name",
                      batch_id='season-batch', playlist_id='ss46089', preferred_quality='cap:1080p',
                      resolve_before_download=True, embed_thumbnail=True, embed_metadata=True,
                      embed_chapters=True, remux_container='mkv', clip_enabled=True,
                      clip_start=8, clip_end=68, subtitle_languages=('zh-Hans',))
    request = replace(request, video=replace(request.video, canonical_thumbnail_url='https://example.org/canonical.png'))
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

    def enqueue(value):
        calls.append(value)
        page.add_task(value)
    monkeypatch.setattr(controller.queue, "enqueue", enqueue)
    monkeypatch.setattr(controller.metadata_process, "start", lambda *args: pytest.fail('Retry must not parse'))
    page.set_url('https://www.bilibili.com/bangumi/play/ss46089')
    page.taskAction(request.task_id, "retry")
    assert len(calls) == 1
    assert calls[0] == replace(request, resume_partial=True)
    assert page.state["url"].endswith('/ss46089')
    assert page.task_status(request.task_id) is TaskStatus.RESUMING
    page.taskAction(request.task_id, "retry")
    assert len(calls) == 1
    assert not page.state["busy"]
    assert not controller.queue.is_busy
    assert controller.history.get(request.task_id).status is TaskStatus.PENDING
    assert len(controller.history.list_records()) == 1
    controller._shutdown_background_operations()
    controller.window.update(allowClose=True)
    controller.window.close()
    controller.window.dispose()

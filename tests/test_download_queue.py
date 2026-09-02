from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import time

from PySide6.QtCore import QCoreApplication

from test_download_service import _request
from yt_downloader.core.models import DownloadProgress, DownloadResult, TaskStatus
from yt_downloader.workers.download_queue import DownloadQueueController


class ControlledService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.running = 0
        self.maximum_running = 0

    def download(self, request, callback, cancel_event):
        self.calls.append(request.task_id)
        self.running += 1
        self.maximum_running = max(self.maximum_running, self.running)
        callback(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 50, 1, 2, 1000, 1))
        time.sleep(0.03)
        self.running -= 1
        return DownloadResult(request.task_id, request.output_directory / f"{request.task_id}.mp4", 2, "now")


def test_queue_runs_only_one_download_at_a_time(qtbot, tmp_path: Path) -> None:
    service = ControlledService()
    queue = DownloadQueueController(service)
    first = replace(_request(tmp_path), task_id="one")
    second = replace(_request(tmp_path), task_id="two")
    completed: list[str] = []
    queue.completed.connect(lambda result: completed.append(result.task_id))

    queue.enqueue(first)
    queue.enqueue(second)

    qtbot.waitUntil(lambda: completed == ["one", "two"] and not queue.is_busy, timeout=3000)
    assert service.calls == ["one", "two"]
    assert service.maximum_running == 1
    assert queue.is_busy is False

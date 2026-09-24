from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
import time

from PySide6.QtCore import QCoreApplication

from test_download_service import _request
from yt_downloader.core.errors import CancellationCleanupReport, OperationCancelled
from yt_downloader.core.models import DownloadProgress, DownloadResult, TaskStatus
from yt_downloader.workers.download_queue import DownloadQueueController


class PausingService:
    def __init__(self, partial):
        self.partial = partial
        self.started = threading.Event()
        self.calls = []

    def download(self, request, callback, control):
        self.calls.append(request)
        if not request.resume_partial:
            self.partial.parent.mkdir(parents=True, exist_ok=True)
            self.partial.write_bytes(b'partial fixture')
            callback(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 25, 25, 100))
            self.started.set()
            assert control.wait(2)
            if control.is_paused() and not control.is_cancelled():
                from yt_downloader.core.errors import OperationPaused
                raise OperationPaused()
            raise OperationCancelled()
        assert self.partial.read_bytes() == b'partial fixture'
        return DownloadResult(request.task_id, request.output_directory / 'done.mp4', 4, 'now')


def test_pause_resume_preserves_owned_partial_and_cookie_snapshot(qtbot, tmp_path):
    from yt_downloader.core.models import CookieProfile
    from yt_downloader.services.task_artifacts import TaskArtifactRegistry
    request = replace(_request(tmp_path), task_id='pause-resume',
                      cookie_profile=CookieProfile('x', 'X', 'browser', browser='firefox', domain_hint='x.com'))
    partial = TaskArtifactRegistry(tmp_path, request.task_id).workspace / 'download.mp4.part'
    service = PausingService(partial)
    queue = DownloadQueueController(service, max_concurrent=1)
    paused, completed = [], []
    queue.paused.connect(paused.append)
    queue.completed.connect(lambda result: completed.append(result.task_id))
    queue.enqueue(request)
    qtbot.waitUntil(service.started.is_set, timeout=3000)
    qtbot.waitUntil(lambda: queue.pause_task(request.task_id), timeout=3000)
    qtbot.waitUntil(lambda: paused == [request.task_id], timeout=3000)
    assert partial.read_bytes() == b'partial fixture'
    assert queue.task_position(request.task_id) == 'paused'
    assert queue.resume_task(request.task_id)
    qtbot.waitUntil(lambda: completed == [request.task_id] and not queue.is_busy, timeout=3000)
    assert [item.resume_partial for item in service.calls] == [False, True]
    assert service.calls[1].cookie_profile == request.cookie_profile


def test_cancel_paused_task_cleans_only_owned_workspace(qtbot, tmp_path):
    from yt_downloader.services.task_artifacts import TaskArtifactRegistry
    request = replace(_request(tmp_path), task_id='pause-cancel')
    partial = TaskArtifactRegistry(tmp_path, request.task_id).workspace / 'download.mp4.part'
    unrelated = tmp_path / 'keep.txt'
    unrelated.write_text('keep', encoding='utf-8')
    queue = DownloadQueueController(PausingService(partial))
    paused, cancelled = [], []
    queue.paused.connect(paused.append)
    queue.cancelled.connect(lambda _task, report: cancelled.append(report))
    queue.enqueue(request)
    qtbot.waitUntil(lambda: queue.pause_task(request.task_id), timeout=3000)
    qtbot.waitUntil(lambda: paused == [request.task_id], timeout=3000)
    assert queue.cancel(request.task_id)
    assert cancelled[0].succeeded
    assert not partial.exists()
    assert unrelated.read_text(encoding='utf-8') == 'keep'


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
    queue = DownloadQueueController(service, max_concurrent=1)
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


def test_queue_reports_active_and_pending_task_positions(qtbot, tmp_path: Path) -> None:
    service = ControlledService()
    queue = DownloadQueueController(service, max_concurrent=1)
    first = replace(_request(tmp_path), task_id="active-position")
    second = replace(_request(tmp_path), task_id="pending-position")

    queue.enqueue(first)
    queue.enqueue(second)

    assert queue.task_position(first.task_id) == "active"
    assert queue.task_position(second.task_id) == "pending"
    qtbot.waitUntil(lambda: not queue.is_busy, timeout=3000)
    assert queue.task_position(first.task_id) is None


class LockingCancellableService:
    def __init__(self, locked_path: Path) -> None:
        self.locked_path = locked_path
        self.started = threading.Event()
        self.worker_exited = threading.Event()

    def download(self, request, callback, cancel_event):
        try:
            with self.locked_path.open("wb") as handle:
                handle.write(b"partial")
                handle.flush()
                callback(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 25, 25, 100, 1000, 3))
                self.started.set()
                assert cancel_event.wait(2)
                # A late provider callback after Cancel must not reach the UI.
                callback(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO, 75, 75, 100, 900, 1))
        finally:
            self.worker_exited.set()
        raise OperationCancelled(
            cleanup_report=CancellationCleanupReport(
                task_id=request.task_id,
                output_directory=str(request.output_directory),
            ),
        )


def test_cancelled_is_emitted_only_after_thread_exit_and_file_unlock(qtbot, tmp_path: Path) -> None:
    partial = tmp_path / "video.mp4.part"
    service = LockingCancellableService(partial)
    queue = DownloadQueueController(service)
    request = replace(_request(tmp_path), task_id="cancel-me")
    lifecycle: list[str] = []
    progress: list[DownloadProgress] = []
    unlocked_during_cancelled: list[bool] = []
    cleanup_reports: list[CancellationCleanupReport] = []

    queue.cancelling.connect(lambda task_id: lifecycle.append(f"cancelling:{task_id}"))
    queue.progress.connect(progress.append)

    def on_cancelled(task_id: str, report: CancellationCleanupReport) -> None:
        probe = partial.with_suffix(".unlock-probe")
        partial.rename(probe)
        probe.rename(partial)
        unlocked_during_cancelled.append(True)
        cleanup_reports.append(report)
        lifecycle.append(f"cancelled:{task_id}")

    queue.cancelled.connect(on_cancelled)
    queue.enqueue(request)
    qtbot.waitUntil(service.started.is_set, timeout=2000)

    assert queue.cancel(request.task_id) is True
    qtbot.waitUntil(lambda: lifecycle[-1:] == ["cancelled:cancel-me"], timeout=3000)

    assert lifecycle == ["cancelling:cancel-me", "cancelled:cancel-me"]
    assert service.worker_exited.is_set()
    assert unlocked_during_cancelled == [True]
    assert cleanup_reports[0].succeeded
    assert cleanup_reports[0].task_id == request.task_id
    assert [event.percent for event in progress] == [25]
    assert queue.is_busy is False

from dataclasses import replace
import threading
import time

import pytest
from test_download_service import _request
from yt_downloader.core.models import DownloadResult
from yt_downloader.workers.download_queue import DownloadQueueController


@pytest.mark.parametrize('limit', [1, 2, 3, 4])
def test_global_concurrency_is_shared_and_bounded(qtbot, tmp_path, limit):
    class Service:
        running = 0
        maximum = 0
        lock = threading.Lock()
        def download(self, request, callback, cancel):
            with self.lock:
                self.running += 1
                self.maximum = max(self.maximum, self.running)
            time.sleep(0.1)
            with self.lock:
                self.running -= 1
            return DownloadResult(request.task_id, tmp_path / 'file', 1, 'now')
    service = Service()
    queue = DownloadQueueController(service, max_concurrent=limit)
    done = []
    queue.completed.connect(done.append)
    for i in range(8):
        queue.enqueue(replace(_request(tmp_path), task_id=str(i)))
    qtbot.waitUntil(lambda: not queue.is_busy, timeout=5000)
    assert len(done) == 8
    assert service.maximum == limit


def test_download_service_does_not_serialize_independent_tasks(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from test_download_service import FakeYDL
    from yt_downloader.services.download_service import DownloadService
    gate = threading.Barrier(2, timeout=2)
    class ConcurrentYDL(FakeYDL):
        def download(self, urls):
            gate.wait()
            return super().download(urls)
    service = DownloadService(ydl_factory=ConcurrentYDL, require_tools=False, media_validator=lambda path: True)
    def run(index):
        request = replace(_request(tmp_path), task_id=str(index), filename_stem=str(index))
        return service.download(request, lambda event: None, threading.Event())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (1, 2)))
    assert all(result.file_path.is_file() for result in results)


def test_paused_batch_does_not_block_other_batch_and_cancellation_is_independent(qtbot, tmp_path):
    from yt_downloader.core.errors import AppError
    class Service:
        calls = []
        def download(self, request, callback, cancel):
            self.calls.append(request.task_id)
            if request.task_id == 'bad':
                raise AppError('test', 'Failed', 'fixture')
            return DownloadResult(request.task_id, tmp_path / request.task_id, 1, 'now')
    service = Service()
    queue = DownloadQueueController(service, max_concurrent=1)
    queue.pause('paused')
    queue.enqueue(replace(_request(tmp_path), task_id='wait', batch_id='paused'))
    queue.enqueue(replace(_request(tmp_path), task_id='cancel', batch_id='paused'))
    queue.enqueue(replace(_request(tmp_path), task_id='bad', batch_id='other'))
    queue.enqueue(replace(_request(tmp_path), task_id='good', batch_id='other'))
    done, failed, cancelled = [], [], []
    queue.completed.connect(lambda r: done.append(r.task_id))
    queue.failed.connect(lambda task, error: failed.append(task))
    queue.cancelled.connect(lambda task, report: cancelled.append(task))
    qtbot.waitUntil(lambda: done == ['good'], timeout=3000)
    assert service.calls == ['bad', 'good']
    assert failed == ['bad']
    queue.cancel('cancel')
    queue.resume('paused')
    qtbot.waitUntil(lambda: not queue.is_busy, timeout=3000)
    assert done == ['good', 'wait']
    assert cancelled == ['cancel']


def test_progress_from_two_active_tasks_is_not_dropped(qapp):
    from yt_downloader.ui.progress_dispatch import ProgressEventCoalescer
    from yt_downloader.core.models import DownloadProgress, TaskStatus
    dispatch = ProgressEventCoalescer()
    received = []
    dispatch.dispatched.connect(received.append)
    for percent in (1, 2, 3):
        for task in ('a', 'b'):
            dispatch.push(DownloadProgress(task, TaskStatus.DOWNLOADING_VIDEO, percent))
    dispatch.flush()
    assert {p.task_id for p in received if p.percent == 3} == {'a', 'b'}


def test_global_download_limit_is_persisted_separately_from_fragments(tmp_path):
    from dataclasses import replace
    import pytest
    from yt_downloader.services.settings_service import SettingsService
    store = SettingsService(tmp_path/'settings.json', default_download_directory=tmp_path)
    assert store.defaults().max_concurrent_downloads == 2
    store.save(replace(store.defaults(), max_concurrent_downloads=4, concurrent_fragments=8))
    assert store.load().max_concurrent_downloads == 4
    with pytest.raises(ValueError):
        store.save(replace(store.defaults(), max_concurrent_downloads=5))


def test_concurrent_same_title_outputs_never_replace_each_other(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from yt_downloader.services.task_artifacts import TaskArtifactRegistry
    gate = threading.Barrier(8)
    def write(index):
        registry = TaskArtifactRegistry(tmp_path, str(index))
        registry.prepare()
        candidate = registry.download_path('mp4')
        candidate.write_text(str(index))
        gate.wait()
        result = registry.commit(candidate, tmp_path / 'same-title.mp4')
        registry.cleanup()
        return result
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(write, range(8)))
    assert len(set(paths)) == 8
    assert {p.read_text() for p in paths} == {str(i) for i in range(8)}

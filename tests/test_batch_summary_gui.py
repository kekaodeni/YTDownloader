from dataclasses import replace

import pytest
from PySide6.QtCore import QMetaObject, Qt
from conftest import click_item, find_item, run_frames
from scripts.verify_quick_ui import sample_video
from yt_downloader.core.models import DownloadRequest, DownloadResult, TaskStatus


@pytest.mark.parametrize('count,failed', [(2, 0), (28, 0), (28, 2), (1, 0)])
@pytest.mark.parametrize('reduced', [False, True])
def test_batch_summary_real_qt_geometry_and_details(quick_window, qapp, tmp_path, count, failed, reduced):
    page = quick_window.download_page
    quick_window.update(reduceMotion=reduced)
    video = sample_video()
    page.show_video(video)
    requests = [DownloadRequest(f'batch-{i}', video, video.formats[0], tmp_path, f'video-{i}', batch_id='gui') for i in range(count)]
    page.register_batch(requests)
    for request in requests:
        page.add_task(request)
    run_frames(qapp)
    view = find_item(quick_window, 'taskList')
    assert view.property('count') == count
    view.setProperty('contentY', view.property('originY') + 80)
    run_frames(qapp, 60)
    before = view.property('contentY') - view.property('originY')
    for request in requests[:-1]:
        if int(request.task_id.split('-')[1]) >= count - failed:
            page.fail_task(request.task_id, TaskStatus.FAILED)
        else:
            page.complete_task(DownloadResult(request.task_id, tmp_path / request.filename_stem, 100, 'now'))
        assert page._tasks.count == count
    last = requests[-1]
    if failed:
        page.fail_task(last.task_id, TaskStatus.FAILED)
    else:
        page.complete_task(DownloadResult(last.task_id, tmp_path / last.filename_stem, 100, 'now'))
    run_frames(qapp, 650)
    assert view.property('count') == (1 + failed if count > 1 else 1)
    assert abs(view.property('contentY') - view.property('originY') - before) < 2
    assert not quick_window.grab().isNull()
    if count > 1:
        summary = find_item(quick_window, 'summary:gui')
        old_height = summary.height()
        page.summaryAction('summary:gui', 'details')
        run_frames(qapp, 650)
        assert summary.height() > old_height
        assert abs(view.property('contentY') - view.property('originY') - before) < 2
        page.summaryAction('summary:gui', 'details')
        run_frames(qapp, 650)
        assert abs(summary.height() - old_height) < 2
    assert not quick_window.qml_warnings

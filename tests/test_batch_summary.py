from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_download_service import _request
from yt_downloader.core.models import DownloadResult, TaskStatus
from yt_downloader.ui.quick_download import DownloadPresenter


def batch(page, tmp_path, count, batch_id='batch'):
    requests = [replace(_request(tmp_path), task_id=f'{batch_id}-{i}', batch_id=batch_id) for i in range(count)]
    page.register_batch(requests)
    for request in requests:
        page.add_task(request)
    return requests


def finish(page, request):
    page.complete_task(DownloadResult(request.task_id, request.output_directory / f'{request.task_id}.mkv', 100, '2026-10-06'))


@pytest.fixture
def page(qapp, tmp_path):
    return DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))


def test_completed_children_do_not_collapse_before_batch_terminal(page, tmp_path):
    requests = batch(page, tmp_path, 28)
    ids = [row['id'] for row in page._tasks.rows]
    for request in requests[:-1]:
        finish(page, request)
        assert [row['id'] for row in page._tasks.rows] == ids


@pytest.mark.parametrize('count', [2, 28])
def test_success_tasks_collapse_to_one_summary(page, tmp_path, count):
    for request in batch(page, tmp_path, count):
        finish(page, request)
    assert page._tasks.count == 1
    assert page._tasks.rows[0]['kind'] == 'summary'
    assert page._tasks.rows[0]['completed'] == count
    assert len(page._tasks.rows[0]['details']) == count


def test_failed_children_remain_visible(page, tmp_path):
    requests = batch(page, tmp_path, 28)
    for request in requests[:26]:
        finish(page, request)
    for request in requests[26:]:
        page.fail_task(request.task_id, TaskStatus.FAILED)
    assert page._tasks.count == 3
    summary = next(row for row in page._tasks.rows if row.get('kind') == 'summary')
    assert (summary['completed'], summary['failed']) == (26, 2)
    assert all(page.task_status(r.task_id) is TaskStatus.FAILED for r in requests[26:])


def test_cancelled_children_are_compact(page, tmp_path):
    requests = batch(page, tmp_path, 3)
    finish(page, requests[0])
    for request in requests[1:]:
        page.fail_task(request.task_id, TaskStatus.CANCELLED)
    assert page._tasks.count == 1
    assert page._tasks.rows[0]['cancelled'] == 2


def test_batch_summary_details_expand(page, tmp_path):
    for request in batch(page, tmp_path, 2):
        finish(page, request)
    page.summaryAction(page._tasks.rows[0]['id'], 'details')
    assert page._tasks.rows[0]['expanded']
    page.summaryAction(page._tasks.rows[0]['id'], 'details')
    assert not page._tasks.rows[0]['expanded']


def test_single_task_keeps_normal_completed_card(page, tmp_path):
    for request in batch(page, tmp_path, 1):
        finish(page, request)
    assert page._tasks.rows[0].get('kind') != 'summary'


def test_retry_updates_summary_without_expanding_successful_siblings(page, tmp_path):
    requests = batch(page, tmp_path, 3)
    finish(page, requests[0]); finish(page, requests[1])
    page.fail_task(requests[2].task_id, TaskStatus.FAILED)
    page.add_task(replace(requests[2], resume_partial=True))
    assert page._tasks.count == 2
    assert page._tasks.rows[0]['completed'] == 2
    finish(page, requests[2])
    assert page._tasks.count == 1
    assert page._tasks.rows[0]['completed'] == 3


def test_all_failed_batch_keeps_all_retry_cards(page, tmp_path):
    for request in batch(page, tmp_path, 3):
        page.fail_task(request.task_id, TaskStatus.FAILED)
    assert page._tasks.count == 3
    assert all(row['retry'] for row in page._tasks.rows)


def test_cancel_and_delete_does_not_prevent_batch_completion(page, tmp_path):
    requests = batch(page, tmp_path, 3)
    page.fail_task(requests[0].task_id, TaskStatus.CANCELLED)
    page.remove_task(requests[0].task_id)
    finish(page, requests[1]); finish(page, requests[2])
    assert page._tasks.count == 1
    assert page._tasks.rows[0]['completed'] == 2
    assert page._tasks.rows[0]['cancelled'] == 1


def test_new_batch_replaces_old_success_summary_and_keeps_failures(page, tmp_path):
    requests = batch(page, tmp_path, 3, 'old')
    finish(page, requests[0]); finish(page, requests[1])
    page.fail_task(requests[2].task_id, TaskStatus.FAILED)
    batch(page, tmp_path, 2, 'new')
    assert not any(row.get('kind') == 'summary' for row in page._tasks.rows)
    assert page.task_status(requests[2].task_id) is TaskStatus.FAILED
    assert page._tasks.count == 3

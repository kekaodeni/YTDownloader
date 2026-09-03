from types import SimpleNamespace

from yt_downloader.app import AppController
from yt_downloader.core.errors import CancellationCleanupReport
from yt_downloader.core.models import TaskStatus


def test_cancelled_task_is_persisted_before_remove_intent_retires_card() -> None:
    controller = AppController.__new__(AppController)
    controller._remove_intents = {"task"}
    lifecycle: list[str] = []
    controller.window = SimpleNamespace(download_page=SimpleNamespace(
        fail_task=lambda *_args: lifecycle.append("terminal-ui"),
        remove_task=lambda _task_id: lifecycle.append("remove-card"),
    ))
    controller.history = SimpleNamespace(
        update_status=lambda *_args, **_kwargs: lifecycle.append("persist-history")
    )
    controller.refresh_history = lambda: lifecycle.append("refresh-history")
    controller._confirm_remove_after_incomplete_cleanup = lambda _report: True
    report = CancellationCleanupReport(task_id="task", output_directory="D:/Videos")

    controller._cancelled("task", report)

    assert lifecycle == [
        "terminal-ui",
        "persist-history",
        "refresh-history",
        "remove-card",
    ]
    assert "task" not in controller._remove_intents


def test_pending_remove_intent_cancels_queue_before_card_disappears() -> None:
    controller = AppController.__new__(AppController)
    controller._remove_intents = set()
    lifecycle: list[str] = []
    controller.queue = SimpleNamespace(
        task_position=lambda _task_id: "pending",
        cancel=lambda task_id: lifecycle.append(f"cancel:{task_id}") or True,
    )
    controller.window = SimpleNamespace(download_page=SimpleNamespace(
        task_request=lambda _task_id: None,
        remove_task=lambda _task_id: lifecycle.append("remove-card"),
    ))

    controller._remove_task_requested("queued")

    assert lifecycle == ["cancel:queued"]
    assert controller._remove_intents == {"queued"}


def test_terminal_card_removal_does_not_change_history() -> None:
    controller = AppController.__new__(AppController)
    controller._remove_intents = set()
    removed: list[str] = []
    controller.queue = SimpleNamespace(task_position=lambda _task_id: None)
    controller.window = SimpleNamespace(download_page=SimpleNamespace(
        remove_task=removed.append,
    ))
    controller.history = SimpleNamespace(update_status=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    controller._remove_task_requested("terminal")

    assert removed == ["terminal"]

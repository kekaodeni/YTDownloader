import pytest

from yt_downloader.core.models import TaskStatus
from yt_downloader.core.state_machine import ensure_transition


def test_rejects_impossible_download_state_transition() -> None:
    ensure_transition(TaskStatus.PENDING, TaskStatus.DOWNLOADING_VIDEO)
    ensure_transition(TaskStatus.DOWNLOADING_VIDEO, TaskStatus.MERGING)
    ensure_transition(TaskStatus.MERGING, TaskStatus.COMPLETED)
    with pytest.raises(ValueError):
        ensure_transition(TaskStatus.COMPLETED, TaskStatus.DOWNLOADING_VIDEO)


def test_user_cancellation_has_an_explicit_non_terminal_stage() -> None:
    ensure_transition(TaskStatus.DOWNLOADING_VIDEO, TaskStatus.CANCELLING)
    ensure_transition(TaskStatus.CANCELLING, TaskStatus.CANCELLED)
    with pytest.raises(ValueError):
        ensure_transition(TaskStatus.CANCELLING, TaskStatus.DOWNLOADING_AUDIO)

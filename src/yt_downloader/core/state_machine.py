"""Explicit legal task transitions, independent of translated UI text."""

from __future__ import annotations

from yt_downloader.core.models import TaskStatus


_TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
_ALLOWED: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.FETCHING_METADATA, TaskStatus.DOWNLOADING_VIDEO, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.FETCHING_METADATA: {TaskStatus.READY, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.READY: {TaskStatus.PENDING, TaskStatus.DOWNLOADING_VIDEO, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.DOWNLOADING_VIDEO: {
        TaskStatus.DOWNLOADING_AUDIO, TaskStatus.MERGING, TaskStatus.POST_PROCESSING,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
    },
    TaskStatus.DOWNLOADING_AUDIO: {
        TaskStatus.MERGING, TaskStatus.POST_PROCESSING, TaskStatus.COMPLETED,
        TaskStatus.FAILED, TaskStatus.CANCELLED,
    },
    TaskStatus.MERGING: {TaskStatus.POST_PROCESSING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.POST_PROCESSING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return current == target or target in _ALLOWED[current]


def ensure_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Illegal task transition: {current.value} -> {target.value}")


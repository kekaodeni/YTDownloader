"""Coalesces same-turn task additions with terminal-card retirement."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget


class TaskCardTransitionController(QObject):
    flush_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pending: dict[str, QWidget] = {}
        self._scheduled = False
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._request_flush)

    def stage(self, task_id: str, card: QWidget) -> None:
        self._pending[task_id] = card
        if not self._scheduled:
            self._scheduled = True
            self._flush_timer.start(0)

    def take_pending(self) -> tuple[tuple[str, QWidget], ...]:
        values = tuple(self._pending.items())
        self._pending.clear()
        return values

    def discard(self, task_id: str) -> None:
        self._pending.pop(task_id, None)

    def _request_flush(self) -> None:
        self._scheduled = False
        self.flush_requested.emit()

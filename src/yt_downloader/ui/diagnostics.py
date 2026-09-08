"""Opt-in UI timing counters used by validation builds and tests."""
from __future__ import annotations

from collections import deque
from math import ceil
import time
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication


class ReducedMotionPolicy(QObject):
    changed = Signal(bool)

    def __init__(self, enabled: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.enabled = bool(enabled)

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled != self.enabled:
            self.enabled = enabled
            self.changed.emit(enabled)


class UIAnimationDiagnostics(QObject):
    def __init__(self, parent: QObject | None = None, *, interval_ms: int = 8) -> None:
        super().__init__(parent)
        self.interval_ms = interval_ms
        self.paint_events = 0
        self.layout_requests = 0
        self._stalls: deque[float] = deque(maxlen=20_000)
        self._providers: list[Callable[[], int]] = []
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._sample)
        self._last = 0.0
        self._app: QApplication | None = None

    def start(self, app: QApplication) -> None:
        if self._app is app:
            return
        self.stop()
        self._app = app
        app.installEventFilter(self)
        self._last = time.perf_counter()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        if self._app is not None:
            self._app.removeEventFilter(self)
            self._app = None

    def register_active_provider(self, provider: Callable[[], int]) -> None:
        self._providers.append(provider)

    def eventFilter(self, _watched, event) -> bool:
        if event.type() is QEvent.Type.Paint:
            self.paint_events += 1
        elif event.type() is QEvent.Type.LayoutRequest:
            self.layout_requests += 1
        return False

    def _sample(self) -> None:
        now = time.perf_counter()
        self.record_stall(max(0.0, (now - self._last) * 1000 - self.interval_ms))
        self._last = now

    def record_stall(self, milliseconds: float) -> None:
        self._stalls.append(max(0.0, float(milliseconds)))

    @staticmethod
    def _percentile(values: list[float], proportion: float) -> float:
        if not values:
            return 0.0
        return values[max(0, ceil(len(values) * proportion) - 1)]

    def report(self) -> dict[str, int | float]:
        values = sorted(self._stalls)
        active = sum(max(0, int(provider())) for provider in self._providers)
        return {
            'samples': len(values),
            'p95_ms': self._percentile(values, 0.95),
            'p99_ms': self._percentile(values, 0.99),
            'max_ms': values[-1] if values else 0.0,
            'over_50ms': sum(value > 50 for value in values),
            'serious_regressions': sum(value > 100 for value in values),
            'paint_events': self.paint_events,
            'layout_requests': self.layout_requests,
            'active_visual_objects': active,
        }

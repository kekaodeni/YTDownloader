"""Opt-in frame submission measurements; independent of event-loop timer delays."""
from collections import deque
from math import ceil
from threading import Lock
from time import perf_counter
from PySide6.QtCore import QObject, QTimer, Qt, Slot

class MotionProbe(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.frames = deque(maxlen=30000)
        self.stalls = []
        self.lock = Lock()
        self.changes = 0
        self.navigation = QTimer(self)
        self.navigation.setInterval(160)
        self.navigation.setTimerType(Qt.PreciseTimer)
        self.navigation.timeout.connect(self._navigate)
        self.timer = QTimer(self)
        self.timer.setInterval(8)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self.started = self.last_tick = perf_counter()
        self.window.root.frameSwapped.connect(self._frame, Qt.DirectConnection)
        self.navigation.start()
        self.timer.start()

    @Slot()
    def _frame(self):
        now = perf_counter()
        if now - self.started > 2:
            with self.lock:
                self.frames.append(now)

    def _navigate(self):
        self.changes += 1
        self.window._select_page(self.changes % 4)

    def _tick(self):
        now = perf_counter()
        if now - self.started > 2:
            self.stalls.append(max(0, (now-self.last_tick)*1000-8))
        self.last_tick = now

    def stop(self):
        self.navigation.stop()
        self.timer.stop()
        self.window.root.frameSwapped.disconnect(self._frame)
        with self.lock:
            stamps = list(self.frames)
        intervals = [(b-a)*1000 for a,b in zip(stamps,stamps[1:])]
        def stats(values):
            values = sorted(values)
            return dict(samples=len(values), p95_ms=values[max(0,ceil(len(values)*.95)-1)] if values else 0,
                        p99_ms=values[max(0,ceil(len(values)*.99)-1)] if values else 0,
                        max_ms=max(values,default=0), over_50ms=sum(v>50 for v in values))
        hz = self.window.root.screen().refreshRate()
        frame = stats(intervals)
        return dict(method='QQuickWindow.frameSwapped direct render-thread timestamps; continuous 160 ms navigation retargeting; 2 s warmup excluded',
                    actual_screen_hz=hz, frame_submission=frame, event_loop_delay=stats(self.stalls),
                    threshold_p95_ms=2000/hz, threshold_p99_ms=3000/hz,
                    passed=bool(intervals) and frame['p95_ms']<=2000/hz and frame['p99_ms']<=3000/hz and frame['over_50ms']==0,
                    raw_intervals_ms=intervals)

"""Display byte throughput from irregular samples on an active-time window."""
from collections import deque
import time


class DownloadSpeedEstimator:
    def __init__(self, *, clock=time.monotonic, window=3.0, alpha=.3):
        self.clock, self.window, self.alpha = clock, window, alpha
        self.samples = deque()
        self.speed = None
        self.last_increase = None
        self.last_bytes = None
        self.paused_at = None

    def sample(self, total_bytes):
        now = self.clock()
        if self.paused_at is not None:
            return None
        if total_bytes is not None and (self.last_bytes is None or total_bytes < self.last_bytes):
            self.samples.clear()
            self.speed = None
            self.last_increase = now
        increased = total_bytes is not None and self.last_bytes is not None and total_bytes > self.last_bytes
        if total_bytes is not None:
            self.samples.append((now, total_bytes))
            self.last_bytes = total_bytes
        while len(self.samples) > 2 and self.samples[1][0] <= now - self.window:
            self.samples.popleft()
        if increased:
            oldest_at, oldest_bytes = self.samples[0]
            if now > oldest_at:
                measured = (total_bytes - oldest_bytes) / (now - oldest_at)
                self.speed = measured if self.speed is None else self.alpha * measured + (1 - self.alpha) * self.speed
            self.last_increase = now
        stalled = now - self.last_increase if self.last_increase is not None else 0
        if self.speed is None or stalled < 2:
            return self.speed
        if stalled >= 5:
            return 0.0
        return self.speed * .7 ** (stalled - 2)

    def pause(self):
        self.paused_at = self.clock()

    def resume(self):
        if self.paused_at is None:
            return
        gap = self.clock() - self.paused_at
        self.samples = deque((stamp + gap, size) for stamp, size in self.samples)
        if self.last_increase is not None:
            self.last_increase += gap
        self.paused_at = None

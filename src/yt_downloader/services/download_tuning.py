"""Pure policy helpers for selecting a conservative fragment concurrency."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Mapping, Sequence


SUPPORTED_FRAGMENT_COUNTS = (1, 4, 8)
AUTO_FRAGMENT_COUNT = 1


@dataclass(slots=True)
class BenchmarkTrafficBudget:
    limit_bytes: int = 1_500_000_000
    consumed_bytes: int = 0

    def record(self, transferred_bytes: int) -> None:
        self.consumed_bytes += max(0, int(transferred_bytes))

    def can_start(self, expected_bytes: int | None) -> bool:
        if expected_bytes is None:
            return self.consumed_bytes < self.limit_bytes
        return self.consumed_bytes + max(0, int(expected_bytes)) <= self.limit_bytes


def needs_third_sample(
    samples: Sequence[float],
    *,
    relative_spread: float = 0.15,
) -> bool:
    positive = [float(value) for value in samples if value > 0]
    if len(positive) != 2:
        return False
    low, high = sorted(positive)
    return (high - low) / low > relative_spread


def choose_auto_fragment_count(
    throughput_samples: Mapping[int, Sequence[float]],
    failed_counts: Mapping[int, int],
    *,
    within_fastest: float = 0.05,
) -> int:
    """Choose the lowest error-free concurrency within 5% of the fastest median."""
    medians = {
        count: median(values)
        for count, values in throughput_samples.items()
        if count in SUPPORTED_FRAGMENT_COUNTS and values and failed_counts.get(count, 0) == 0
    }
    if not medians:
        return AUTO_FRAGMENT_COUNT
    fastest = max(medians.values())
    threshold = fastest * (1.0 - within_fastest)
    return min(count for count, value in medians.items() if value >= threshold)

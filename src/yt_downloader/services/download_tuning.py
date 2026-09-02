"""Pure policy helpers for selecting a conservative fragment concurrency."""

from __future__ import annotations

from statistics import median
from typing import Mapping, Sequence


SUPPORTED_FRAGMENT_COUNTS = (1, 4, 8)
AUTO_FRAGMENT_COUNT = 1


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

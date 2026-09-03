from yt_downloader.services.download_tuning import (
    BenchmarkTrafficBudget,
    choose_auto_fragment_count,
    needs_third_sample,
)


def test_auto_concurrency_uses_median_and_lowest_count_within_five_percent() -> None:
    samples = {
        1: [9.6, 10.0, 10.4],
        4: [10.2, 10.3, 30.0],
        8: [10.4, 10.5, 10.6],
    }

    assert choose_auto_fragment_count(samples, {}) == 1


def test_auto_concurrency_rejects_failed_configuration_and_keeps_safe_fallback() -> None:
    samples = {1: [4.0, 4.1, 4.2], 4: [8.0, 8.1, 8.2], 8: [9.0, 9.1, 9.2]}

    assert choose_auto_fragment_count(samples, {4: 1, 8: 1}) == 1
    assert choose_auto_fragment_count({}, {}) == 1


def test_benchmark_budget_counts_failed_transfer_and_blocks_unsafe_next_run() -> None:
    budget = BenchmarkTrafficBudget(limit_bytes=1_500_000_000)

    budget.record(400_000_000)
    budget.record(350_000_000)

    assert budget.consumed_bytes == 750_000_000
    assert budget.can_start(700_000_000)
    assert not budget.can_start(800_000_000)


def test_third_sample_is_only_needed_when_two_results_differ_over_fifteen_percent() -> None:
    assert not needs_third_sample([10.0, 11.0])
    assert needs_third_sample([10.0, 12.0])

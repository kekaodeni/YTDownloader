from yt_downloader.services.download_speed import DownloadSpeedEstimator


def test_unchanged_bytes_do_not_create_zero_speed_spikes():
    now = [0.0]
    estimator = DownloadSpeedEstimator(clock=lambda: now[0])
    assert estimator.sample(0) is None
    now[0] = .5
    speed = estimator.sample(3_500_000)
    assert speed == 7_000_000
    now[0] = 1.0
    assert estimator.sample(3_500_000) == speed
    now[0] = 1.5
    assert estimator.sample(7_500_000) > 0
    now[0] = 2.0
    assert estimator.sample(7_500_000) > 0


def test_real_stall_decays_then_reaches_zero_after_five_seconds():
    now = [0.0]
    estimator = DownloadSpeedEstimator(clock=lambda: now[0])
    estimator.sample(0)
    now[0] = 1
    speed = estimator.sample(7_000_000)
    now[0] = 2.9
    assert estimator.sample(None) == speed
    now[0] = 4
    assert 0 < estimator.sample(7_000_000) < speed
    now[0] = 6
    assert estimator.sample(7_000_000) == 0


def test_pause_time_is_excluded_from_speed_window():
    now = [0.0]
    estimator = DownloadSpeedEstimator(clock=lambda: now[0])
    estimator.sample(0)
    now[0] = 1
    speed = estimator.sample(7_000_000)
    estimator.pause()
    now[0] = 61
    assert estimator.sample(7_000_000) is None
    estimator.resume()
    now[0] = 61.5
    assert estimator.sample(7_000_000) == speed
    now[0] = 62
    assert estimator.sample(14_000_000) == speed


def test_counter_reset_starts_a_new_window():
    now = [0.0]
    estimator = DownloadSpeedEstimator(clock=lambda: now[0])
    estimator.sample(7000)
    now[0] = 1
    assert estimator.sample(14000) == 7000
    now[0] = 2
    assert estimator.sample(0) is None

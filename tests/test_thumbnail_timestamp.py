import pytest

from yt_downloader.services.ffmpeg_service import validate_timestamp


@pytest.mark.parametrize("timestamp", [0, 0.1, 205, 765.99, 766])
def test_accepts_timestamp_within_video_duration(timestamp: float) -> None:
    assert validate_timestamp(timestamp, 766) == float(timestamp)


@pytest.mark.parametrize("timestamp", [-1, 766.1, float("nan"), float("inf")])
def test_rejects_timestamp_outside_video_duration(timestamp: float) -> None:
    with pytest.raises(ValueError):
        validate_timestamp(timestamp, 766)

from yt_downloader.core.models import FormatOption, ProgressTotalSource
from yt_downloader.core.progress import AggregateProgressTracker


def test_fragment_estimates_are_not_locked_as_the_component_total() -> None:
    option = FormatOption(
        label="2160p 4K 60 FPS",
        height=2160,
        fps=60,
        vcodec="vp09.00.51.08",
        acodec="mp4a.40.2",
        container="MP4",
        final_ext="mp4",
        format_selector="628+140-drc",
        estimated_size=None,
        requires_merge=True,
        video_format_id="628",
        audio_format_id="140-drc",
        video_size=None,
        audio_size=2_411_036,
    )
    tracker = AggregateProgressTracker(option)

    first = tracker.update({
        "downloaded_bytes": 712,
        "total_bytes": None,
        "total_bytes_estimate": 712,
        "fragment_index": 0,
        "fragment_count": 28,
        "info_dict": {"format_id": "628"},
    })
    second = tracker.update({
        "downloaded_bytes": 39_872,
        "total_bytes": None,
        "total_bytes_estimate": 2_250_000,
        "fragment_index": 1,
        "fragment_count": 28,
        "info_dict": {"format_id": "628"},
    })

    assert first.total_bytes is None
    assert second.total_bytes is None
    assert second.downloaded_bytes == 39_872

    finished = tracker.update({
        "downloaded_bytes": 428_696_943,
        "total_bytes": None,
        "total_bytes_estimate": 428_696_943,
        "fragment_index": 28,
        "fragment_count": 28,
        "info_dict": {"format_id": "628"},
    }, finished=True)

    assert finished.total_bytes == 431_107_979
    assert finished.downloaded_bytes == 428_696_943
    assert finished.total_is_estimate is False
    assert finished.total_source is ProgressTotalSource.MIXED

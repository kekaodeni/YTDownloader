from yt_downloader.core.models import FormatOption, ProgressTotalSource
from yt_downloader.core.progress import AggregateProgressTracker


def test_native_estimate_can_change_then_promote_to_a_stable_exact_total() -> None:
    option = FormatOption("VP9", 2160, 60, "vp9", "opus", "WebM", "webm", "v+a", None, True, "v", "a", audio_size=100)
    tracker = AggregateProgressTracker(option)
    first = tracker.update({"info_dict": {"format_id": "v"}, "downloaded_bytes": 100, "total_bytes_estimate": 1000})
    second = tracker.update({"info_dict": {"format_id": "v"}, "downloaded_bytes": 200, "total_bytes_estimate": 2000})
    exact = tracker.update({"info_dict": {"format_id": "v"}, "downloaded_bytes": 400, "total_bytes": 1500})
    late_estimate = tracker.update({"info_dict": {"format_id": "v"}, "downloaded_bytes": 700, "total_bytes_estimate": 9000})
    finished_video = tracker.update({"info_dict": {"format_id": "v"}, "downloaded_bytes": 1500, "total_bytes": 1500}, finished=True)
    audio = tracker.update({"info_dict": {"format_id": "a"}, "downloaded_bytes": 50, "total_bytes": 100})
    assert [first.total_bytes, second.total_bytes] == [1100, 2100]
    assert first.total_is_estimate and second.total_is_estimate
    assert [event.total_bytes for event in (exact, late_estimate, finished_video, audio)] == [1600] * 4
    assert not any(event.total_is_estimate for event in (exact, late_estimate, finished_video, audio))
    assert audio.downloaded_bytes == 1550


def test_incomplete_component_totals_stay_unknown_without_inventing_an_audio_size() -> None:
    option = FormatOption("VP9", 2160, 60, "vp9", "opus", "WebM", "webm", "v+a", None, True, "v", "a")
    tracker = AggregateProgressTracker(option)
    video = tracker.update({"info_dict": {"format_id": "v"}, "downloaded_bytes": 50, "total_bytes_estimate": 1000})
    assert video.total_bytes is None
    assert video.downloaded_bytes == 50
    audio = tracker.update({"info_dict": {"format_id": "a"}, "downloaded_bytes": 10, "total_bytes": 100})
    assert audio.total_bytes == 1100
    assert audio.total_is_estimate


def test_native_fragment_estimates_are_visible_but_never_locked_as_exact() -> None:
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
    assert second.total_bytes == 2_250_000 + 2_411_036
    assert second.total_is_estimate is True
    assert second.total_source is ProgressTotalSource.MIXED
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

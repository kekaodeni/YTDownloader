import pytest

from yt_downloader.core.formats import normalize_formats
from yt_downloader.core.models import CodecPreference, FormatOption


def test_normalizes_and_sorts_user_facing_quality_options() -> None:
    formats = [
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "filesize": 10},
        {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 150, "filesize": 12},
        {"format_id": "22", "ext": "mp4", "height": 720, "fps": 30, "vcodec": "avc1.64001F", "acodec": "mp4a.40.2", "filesize": 100},
        {"format_id": "137", "ext": "mp4", "height": 1080, "fps": 30, "vcodec": "avc1.640028", "acodec": "none", "filesize_approx": 200},
        {"format_id": "248", "ext": "webm", "height": 1080, "fps": 30, "vcodec": "vp9", "acodec": "none", "filesize": 180},
        {"format_id": "299", "ext": "mp4", "height": 1080, "fps": 60, "vcodec": "avc1.64002a", "acodec": "none", "filesize": 240},
        {"format_id": "313", "ext": "webm", "height": 2160, "fps": 30, "vcodec": "vp9", "acodec": "none", "filesize": 400},
    ]

    options = normalize_formats(formats)

    assert all(isinstance(option, FormatOption) for option in options)
    assert [option.label for option in options] == ["2160p 4K", "1080p 60 FPS", "1080p", "720p"]
    assert all("137" not in option.label and "313" not in option.label for option in options)

    option_1080 = next(option for option in options if option.label == "1080p")
    assert option_1080.format_selector == "137+140"
    assert option_1080.container == "MP4"
    assert option_1080.requires_merge
    assert option_1080.estimated_size == 210
    assert option_1080.size_is_estimate is True
    assert option_1080.video_size == 200
    assert option_1080.video_size_is_estimate is True
    assert option_1080.audio_size == 10
    assert option_1080.audio_size_is_estimate is False

    option_720 = next(option for option in options if option.label == "720p")
    assert option_720.estimated_size == 100
    assert option_720.size_is_estimate is False

    option_4k = options[0]
    assert option_4k.format_selector == "313+251"
    assert option_4k.container == "WebM"
    assert next(option for option in options if option.is_recommended).label == "1080p"


def test_split_format_has_unknown_size_when_one_required_stream_size_is_missing() -> None:
    options = normalize_formats([
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
        {"format_id": "137", "ext": "mp4", "height": 1080, "fps": 30, "vcodec": "avc1", "acodec": "none", "filesize": 200},
    ])

    assert options[0].requires_merge is True
    assert options[0].estimated_size is None


def test_fragmented_format_does_not_invent_size_from_duration_and_peak_bitrate() -> None:
    options = normalize_formats([
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "filesize": 2_410_324,
        },
        {
            "format_id": "628",
            "ext": "mp4",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "vcodec": "vp09.00.51.08",
            "acodec": "none",
            "tbr": 27_982.889,
            "protocol": "m3u8_native",
        },
    ], duration=149)

    option = options[0]
    assert option.video_size is None
    assert option.video_size_is_estimate is False
    assert option.audio_size == 2_410_324
    assert option.estimated_size is None
    assert option.size_is_estimate is False


def test_portrait_quality_uses_the_short_edge_and_preserves_dimensions() -> None:
    options = normalize_formats([
        {
            "format_id": "portrait",
            "ext": "mp4",
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "vcodec": "avc1",
            "acodec": "mp4a.40.2",
            "filesize": 200,
        },
    ])

    assert options[0].label == "1080p 竖屏"
    assert options[0].width == 1080
    assert options[0].height == 1920


def test_unknown_height_is_kept_without_guessing_from_width() -> None:
    options = normalize_formats([
        {
            "format_id": "unknown-height",
            "ext": "mp4",
            "width": 3840,
            "height": None,
            "fps": None,
            "vcodec": "avc1",
            "acodec": "mp4a.40.2",
        },
    ])

    assert len(options) == 1
    assert options[0].label == "未知清晰度"
    assert options[0].width == 3840
    assert options[0].height is None
    assert options[0].fps is None


def test_auto_codec_policy_uses_ytdlp_native_format_order() -> None:
    options = normalize_formats([
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 129,
            "protocol": "https",
            "filesize": 1_141_383,
            "url": "https://example.invalid/audio",
        },
        {
            "format_id": "628",
            "ext": "mp4",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "vcodec": "vp09.00.51.08",
            "acodec": "none",
            "tbr": 61_229.923,
            "protocol": "m3u8_native",
            "url": "https://example.invalid/hls",
        },
        {
            "format_id": "401",
            "ext": "mp4",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "vcodec": "av01.0.12M.08",
            "acodec": "none",
            "tbr": 19_417.005,
            "protocol": "https",
            "filesize": 170_918_192,
            "url": "https://example.invalid/video",
        },
    ], codec_preference=CodecPreference.AUTO)

    assert options[0].format_selector == "401+140"
    assert options[0].video_format_id == "401"
    assert options[0].estimated_size == 172_059_575
    assert options[0].size_is_estimate is False


@pytest.mark.parametrize(
    ("preference", "expected_id"),
    [
        (CodecPreference.AV1, "401"),
        (CodecPreference.VP9, "628"),
        (CodecPreference.H264, "701"),
    ],
)
def test_explicit_codec_policy_only_filters_candidates_before_ytdlp_ranking(
    preference: CodecPreference,
    expected_id: str,
) -> None:
    shared = {
        "ext": "mp4",
        "width": 3840,
        "height": 2160,
        "fps": 60,
        "acodec": "none",
        "protocol": "https",
    }
    options = normalize_formats([
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "protocol": "https"},
        {**shared, "format_id": "401", "vcodec": "av01.0.12M.08"},
        {**shared, "format_id": "628", "vcodec": "vp09.00.51.08"},
        {**shared, "format_id": "701", "vcodec": "avc1.640033"},
    ], codec_preference=preference)

    assert options[0].video_format_id == expected_id


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (3840, 2160, "2160p 4K"),
        (2560, 1440, "1440p 2K"),
        (1920, 1080, "1080p"),
        (1280, 720, "720p"),
        (854, 480, "480p"),
        (640, 360, "360p"),
        (426, 240, "240p"),
        (256, 144, "144p"),
        (2560, 1080, "1080p"),
    ],
)
def test_landscape_quality_labels_follow_vertical_resolution(
    width: int,
    height: int,
    expected: str,
) -> None:
    option = normalize_formats([
        {
            "format_id": str(height),
            "ext": "mp4",
            "width": width,
            "height": height,
            "fps": None,
            "vcodec": "avc1",
            "acodec": "mp4a.40.2",
        },
    ])[0]

    assert option.label == expected
    assert (option.width, option.height, option.fps) == (width, height, None)

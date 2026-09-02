from yt_downloader.core.models import FormatOption
from yt_downloader.core.formats import normalize_formats


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

    option_4k = options[0]
    assert option_4k.format_selector == "313+251"
    assert option_4k.container == "WebM"
    assert next(option for option in options if option.is_recommended).label == "1080p"

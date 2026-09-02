import pytest

from yt_downloader.core.url import InvalidYoutubeUrl, normalize_youtube_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=tracking", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtube.com/live/dQw4w9WgXcQ?feature=share", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=2", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ],
)
def test_normalizes_supported_single_video_links(raw: str, expected: str) -> None:
    assert normalize_youtube_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/playlist?list=PL123",
        "https://youtube.com/@channel",
        "javascript:alert(1)",
        "https://youtube.com/watch?v=too-short",
    ],
)
def test_rejects_non_video_or_unsafe_links(raw: str) -> None:
    with pytest.raises(InvalidYoutubeUrl):
        normalize_youtube_url(raw)

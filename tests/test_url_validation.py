import pytest

from yt_downloader.core.url import InvalidYoutubeUrl, normalize_media_url, normalize_youtube_url


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.douyin.com/jingxuan?modal_id=7685632626505820153",
        "https://douyin.com/jingxuan?foo=1&modal_id=7685632626505820153&bar=2",
    ],
)
def test_normalizes_douyin_jingxuan_modal_to_standard_video(raw: str) -> None:
    assert normalize_media_url(raw) == "https://www.douyin.com/video/7685632626505820153"


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.douyin.com/video/7685632626505820153",
        "https://www.douyin.com/jingxuan",
        "https://www.douyin.com/jingxuan?modal_id=",
        "https://www.douyin.com/jingxuan?modal_id=abc",
        "https://example.com/jingxuan?modal_id=123",
        "https://www.douyin.com/other?modal_id=123",
        "https://www.douyin.com/jingxuan?modal_id=123&modal_id=456",
        "https://www.douyin.com/jingxuan/?modal_id=123",
        "https://www.douyin.com:8443/jingxuan?modal_id=123",
        "http://www.douyin.com/jingxuan?modal_id=123",
    ],
)
def test_douyin_normalization_leaves_unmatched_urls_unchanged(raw: str) -> None:
    assert normalize_media_url(raw) == raw


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

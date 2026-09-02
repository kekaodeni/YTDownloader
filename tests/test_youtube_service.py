from contextlib import AbstractContextManager
from typing import Any

from yt_downloader.services.youtube_service import YoutubeService


class FakeYdl(AbstractContextManager["FakeYdl"]):
    last_options: dict[str, Any] = {}

    def __init__(self, options: dict[str, Any]) -> None:
        FakeYdl.last_options = options

    def __exit__(self, *_args: object) -> None:
        return None

    def extract_info(self, url: str, *, download: bool) -> dict[str, Any]:
        assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert download is False
        return {
            "id": "dQw4w9WgXcQ",
            "webpage_url": url,
            "title": "测试视频 😀",
            "channel": "测试频道",
            "duration": 65,
            "thumbnail": "https://i.ytimg.com/thumb.jpg",
            "formats": [
                {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128},
                {"format_id": "137", "ext": "mp4", "height": 1080, "fps": 30, "vcodec": "avc1.640028", "acodec": "none"},
            ],
        }

    @staticmethod
    def sanitize_info(info: dict[str, Any]) -> dict[str, Any]:
        return info


class FakeResponse:
    content = b"jpeg-data"

    @staticmethod
    def raise_for_status() -> None:
        return None


def test_fetches_metadata_through_python_api_and_downloads_thumbnail() -> None:
    service = YoutubeService(
        ydl_factory=FakeYdl,
        http_get=lambda *_args, **_kwargs: FakeResponse(),
        deno_path="C:/tools/deno.exe",
        require_deno=False,
    )
    video = service.fetch_metadata("https://youtu.be/dQw4w9WgXcQ?si=tracking")
    assert video.title == "测试视频 😀"
    assert video.channel == "测试频道"
    assert video.thumbnail_bytes == b"jpeg-data"
    assert video.formats[0].label == "1080p"
    assert FakeYdl.last_options["ignoreconfig"] is True
    assert FakeYdl.last_options["noplaylist"] is True
    assert FakeYdl.last_options["remote_components"] == []
    assert FakeYdl.last_options["js_runtimes"]["deno"]["path"].endswith("deno.exe")

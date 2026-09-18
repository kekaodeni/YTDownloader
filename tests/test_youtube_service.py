from contextlib import AbstractContextManager
import threading
from typing import Any

import pytest

from yt_downloader.core.errors import OperationCancelled
from yt_downloader.services.network_policy import NetworkPolicy
from yt_downloader.services.youtube_service import YoutubeService


class FakeYdl(AbstractContextManager["FakeYdl"]):
    last_options: dict[str, Any] = {}

    def __init__(self, options: dict[str, Any]) -> None:
        FakeYdl.last_options = options

    def __exit__(self, *_args: object) -> None:
        return None

    def extract_info(self, url: str, *, download: bool) -> dict[str, Any]:
        assert url.startswith("https://youtu.be/dQw4w9WgXcQ")
        assert download is False
        return {
            "id": "dQw4w9WgXcQ",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "extractor": "youtube", "extractor_key": "Youtube",
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
    assert FakeYdl.last_options["socket_timeout"] == 10
    assert FakeYdl.last_options["retries"] == 1
    assert FakeYdl.last_options["extractor_retries"] == 1


def test_helper_metadata_payload_is_compact_and_thumbnail_is_deferred() -> None:
    requested: list[str] = []
    service = YoutubeService(
        ydl_factory=FakeYdl,
        http_get=lambda url, **_kwargs: requested.append(url),
        deno_path="C:/tools/deno.exe",
        require_deno=False,
    )

    video = service.fetch_metadata(
        "https://youtu.be/dQw4w9WgXcQ",
        include_thumbnail=False,
    )

    assert video.thumbnail_url == "https://i.ytimg.com/thumb.jpg"
    assert video.thumbnail_bytes is None
    assert requested == []
    assert video.raw == {}
    assert video.webpage_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert video.extractor == "youtube"
    assert video.original_url == "https://youtu.be/dQw4w9WgXcQ"



def test_cancellation_after_thumbnail_response_discards_metadata() -> None:
    cancel = threading.Event()

    def cancelling_get(*_args, **_kwargs):
        cancel.set()
        return FakeResponse()

    service = YoutubeService(
        ydl_factory=FakeYdl,
        http_get=cancelling_get,
        deno_path="C:/tools/deno.exe",
        require_deno=False,
    )

    with pytest.raises(OperationCancelled):
        service.fetch_metadata("https://youtu.be/dQw4w9WgXcQ", cancel)


def test_metadata_and_thumbnail_share_the_same_custom_network_policy() -> None:
    calls: list[dict] = []

    class FakeSession:
        trust_env = True

        def get(self, _url, **kwargs):
            calls.append({"trust_env": self.trust_env, **kwargs})
            return FakeResponse()

        def close(self):
            return None

    policy = NetworkPolicy(
        "custom",
        "socks5://127.0.0.1:1080",
        session_factory=FakeSession,
    )
    service = YoutubeService(
        ydl_factory=FakeYdl,
        deno_path="C:/tools/deno.exe",
        require_deno=False,
        network_policy=policy,
    )

    service.fetch_metadata("https://youtu.be/dQw4w9WgXcQ")

    assert FakeYdl.last_options["proxy"] == "socks5://127.0.0.1:1080"
    assert calls[0]["trust_env"] is False
    assert calls[0]["proxies"] == {
        "http": "socks5://127.0.0.1:1080",
        "https": "socks5://127.0.0.1:1080",
    }

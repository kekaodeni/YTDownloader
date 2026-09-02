from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading

from yt_downloader.core.models import (
    DownloadRequest,
    FormatOption,
    TaskStatus,
    VideoInfo,
)
from yt_downloader.services.download_service import DownloadService


def _request(tmp_path: Path) -> DownloadRequest:
    option = FormatOption(
        label="1080p",
        height=1080,
        fps=30,
        vcodec="avc1.640028",
        acodec="mp4a.40.2",
        container="MP4",
        final_ext="mp4",
        format_selector="137+140",
        estimated_size=300,
        requires_merge=True,
        video_format_id="137",
        audio_format_id="140",
        is_recommended=True,
    )
    video = VideoInfo(
        video_id="dQw4w9WgXcQ",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="标题",
        channel="频道",
        duration=42,
        thumbnail_url=None,
        thumbnail_bytes=None,
        formats=(option,),
    )
    return DownloadRequest("task-1", video, option, tmp_path, "标题")


class FakeYDL:
    last_options: dict | None = None

    def __init__(self, options: dict) -> None:
        self.options = options
        FakeYDL.last_options = options

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def download(self, _urls: list[str]) -> int:
        progress = self.options["progress_hooks"][0]
        post = self.options["postprocessor_hooks"][0]
        progress({
            "status": "downloading",
            "downloaded_bytes": 50,
            "total_bytes": 100,
            "speed": 2_000_000,
            "eta": 3,
            "info_dict": {"format_id": "137"},
        })
        progress({"status": "finished", "info_dict": {"format_id": "137"}})
        progress({
            "status": "downloading",
            "downloaded_bytes": 25,
            "total_bytes": 50,
            "speed": 1_000_000,
            "eta": 1,
            "info_dict": {"format_id": "140"},
        })
        progress({"status": "finished", "info_dict": {"format_id": "140"}})
        post({"status": "started", "postprocessor": "Merger"})
        post({"status": "finished", "postprocessor": "Merger"})
        Path(self.options["final_path"]).write_bytes(b"downloaded")
        return 0


def test_download_uses_safe_options_and_reports_real_stages(tmp_path: Path) -> None:
    request = _request(tmp_path)
    existing = tmp_path / "标题.mp4"
    existing.write_bytes(b"existing")
    events = []
    service = DownloadService(
        ydl_factory=FakeYDL,
        deno_path=tmp_path / "deno.exe",
        ffmpeg_path=tmp_path / "ffmpeg.exe",
        require_tools=False,
        media_validator=lambda _path: True,
    )

    result = service.download(request, events.append, threading.Event())

    assert result.file_path.name == "标题 (1).mp4"
    assert result.file_path.read_bytes() == b"downloaded"
    assert existing.read_bytes() == b"existing"
    assert [event.status for event in events] == [
        TaskStatus.DOWNLOADING_VIDEO,
        TaskStatus.DOWNLOADING_AUDIO,
        TaskStatus.MERGING,
        TaskStatus.POST_PROCESSING,
        TaskStatus.COMPLETED,
    ]
    assert events[0].percent == 50
    assert events[0].speed == 2_000_000
    options = FakeYDL.last_options or {}
    assert options["ignoreconfig"] is True
    assert options["noplaylist"] is True
    assert options["continuedl"] is True
    assert options["overwrites"] is False
    assert options["format"] == "137+140"
    assert options["remote_components"] == []
    assert options["merge_output_format"] == "mp4"

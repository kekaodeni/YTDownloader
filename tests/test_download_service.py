from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from yt_dlp.postprocessor import ffmpeg as ytdlp_ffmpeg

from yt_downloader.core.errors import OperationCancelled
from yt_downloader.core.models import (
    DownloadRequest,
    FormatOption,
    ProgressTotalSource,
    TaskStatus,
    VideoInfo,
)
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.network_policy import NetworkPolicy


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
        size_is_estimate=True,
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


class FakeYDLWithMixedTotalSources(FakeYDL):
    def download(self, _urls: list[str]) -> int:
        progress = self.options["progress_hooks"][0]
        progress({
            "status": "downloading",
            "downloaded_bytes": 20,
            "total_bytes": 100,
            "speed": 20,
            "info_dict": {"format_id": "137"},
        })
        Path(self.options["final_path"]).write_bytes(b"downloaded")
        return 0


def test_split_download_combines_hook_total_with_other_component_metadata(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request = replace(
        request,
        format=replace(
            request.format,
            estimated_size=None,
            video_size=None,
            audio_size=50,
            audio_size_is_estimate=False,
        ),
    )
    events = []
    service = DownloadService(
        ydl_factory=FakeYDLWithMixedTotalSources,
        require_tools=False,
        media_validator=lambda _path: True,
    )

    service.download(request, events.append, threading.Event())

    assert events[0].downloaded_bytes == 20
    assert events[0].total_bytes == 150
    assert round(events[0].percent or 0, 2) == 13.33
    assert events[0].total_is_estimate is False
    assert events[0].total_source is ProgressTotalSource.MIXED


class FakeYDLWithoutEta(FakeYDL):
    def download(self, _urls: list[str]) -> int:
        self.options["progress_hooks"][0]({
            "status": "downloading",
            "downloaded_bytes": 100,
            "total_bytes": 1000,
            "speed": 100,
            "eta": None,
            "info_dict": {"format_id": "22"},
        })
        Path(self.options["final_path"]).write_bytes(b"downloaded")
        return 0


def test_missing_provider_eta_falls_back_to_locked_total_and_smoothed_speed(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request = replace(
        request,
        format=replace(
            request.format,
            format_selector="22",
            requires_merge=False,
            video_format_id="22",
            audio_format_id=None,
            estimated_size=1000,
            size_is_estimate=False,
            video_size=1000,
            video_size_is_estimate=False,
            audio_size=None,
        ),
    )
    events = []
    service = DownloadService(
        ydl_factory=FakeYDLWithoutEta,
        require_tools=False,
        media_validator=lambda _path: True,
    )

    service.download(request, events.append, threading.Event())

    assert events[0].eta == 9
    assert events[0].speed == 100


class FakeYDLWithChangingEstimate(FakeYDL):
    def download(self, _urls: list[str]) -> int:
        progress = self.options["progress_hooks"][0]
        progress({
            "status": "downloading",
            "downloaded_bytes": 100,
            "total_bytes_estimate": 1000,
            "speed": 100,
            "eta": None,
            "info_dict": {"format_id": "22"},
        })
        progress({
            "status": "downloading",
            "downloaded_bytes": 200,
            "total_bytes_estimate": 1200,
            "speed": None,
            "eta": None,
            "info_dict": {"format_id": "22"},
        })
        Path(self.options["final_path"]).write_bytes(b"downloaded")
        return 0


def test_first_reliable_estimate_stays_locked_and_missing_speed_is_not_stale(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request = replace(
        request,
        format=replace(
            request.format,
            format_selector="22",
            requires_merge=False,
            video_format_id="22",
            audio_format_id=None,
            estimated_size=None,
            video_size=None,
            audio_size=None,
        ),
    )
    events = []
    ticks = iter((0.0, 0.1))
    service = DownloadService(
        ydl_factory=FakeYDLWithChangingEstimate,
        require_tools=False,
        media_validator=lambda _path: True,
        clock=lambda: next(ticks),
    )

    service.download(request, events.append, threading.Event())

    transfer = events[:-1]
    assert [event.total_bytes for event in transfer] == [1000, 1000]
    assert [event.downloaded_bytes for event in transfer] == [100, 200]
    assert [event.percent for event in transfer] == [10.0, 20.0]
    assert [event.speed for event in transfer] == [100.0, None]
    assert [event.eta for event in transfer] == [9, 8]


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
        network_policy=NetworkPolicy("direct"),
        concurrent_fragments=4,
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
    transfer_events = events[:-1]
    assert [event.total_bytes for event in transfer_events] == [300, 300, 300, 300]
    assert [event.downloaded_bytes for event in transfer_events] == [50, 100, 300, 300]
    assert [round(event.percent or 0, 2) for event in transfer_events] == [16.67, 33.33, 100.0, 100.0]
    assert all(event.total_is_estimate for event in transfer_events)
    assert events[-1].total_bytes == result.file_size
    assert events[-1].total_is_estimate is False
    assert events[0].speed == 2_000_000
    assert events[0].total_source is ProgressTotalSource.METADATA
    assert events[-1].total_source is ProgressTotalSource.FINAL
    options = FakeYDL.last_options or {}
    assert options["ignoreconfig"] is True
    assert options["noplaylist"] is True
    assert options["continuedl"] is True
    assert options["overwrites"] is False
    assert options["format"] == "137+140"
    assert options["remote_components"] == []
    assert options["merge_output_format"] == "mp4"
    assert options["proxy"] == ""
    assert options["concurrent_fragment_downloads"] == 4


class FakeYDLWithFfmpegChild(FakeYDL):
    def download(self, _urls: list[str]) -> int:
        marker = Path(self.options["final_path"]).with_suffix(".child-lock")
        script = (
            "from pathlib import Path; import sys, time; "
            "p=Path(sys.argv[1]); f=p.open('wb'); f.write(b'locked'); f.flush(); "
            "time.sleep(3); f.close()"
        )
        ytdlp_ffmpeg.Popen.run(
            [sys.executable, "-c", script, str(marker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return 0


class FakeYDLWithRapidHooks(FakeYDL):
    def download(self, _urls: list[str]) -> int:
        progress = self.options["progress_hooks"][0]
        for downloaded in (1, 2, 3):
            progress({
                "status": "downloading",
                "downloaded_bytes": downloaded,
                "total_bytes": 10,
                "speed": 1,
                "info_dict": {"format_id": "22"},
            })
        Path(self.options["final_path"]).write_bytes(b"downloaded")
        return 0


def test_progress_events_are_coalesced_to_about_twelve_frames_per_second(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request = replace(
        request,
        format=replace(
            request.format,
            format_selector="22",
            requires_merge=False,
            video_format_id="22",
            audio_format_id=None,
            estimated_size=10,
            video_size=10,
            audio_size=None,
        ),
    )
    events = []
    ticks = iter((0.0, 0.05, 0.081))
    service = DownloadService(
        ydl_factory=FakeYDLWithRapidHooks,
        require_tools=False,
        media_validator=lambda _path: True,
        clock=lambda: next(ticks),
    )

    service.download(request, events.append, threading.Event())

    assert [event.downloaded_bytes for event in events[:-1]] == [1, 3]


def test_cancel_interrupts_task_owned_ffmpeg_and_closes_handles(tmp_path: Path) -> None:
    request = _request(tmp_path)
    cancel = threading.Event()
    marker = (tmp_path / "标题.mp4").with_suffix(".child-lock")
    service = DownloadService(
        ydl_factory=FakeYDLWithFfmpegChild,
        deno_path=tmp_path / "deno.exe",
        ffmpeg_path=tmp_path / "ffmpeg.exe",
        require_tools=False,
        media_validator=lambda _path: True,
    )

    def cancel_after_child_starts() -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.01)
        cancel.set()

    watcher = threading.Thread(target=cancel_after_child_starts)
    watcher.start()
    started = time.monotonic()
    with pytest.raises(OperationCancelled):
        service.download(request, lambda _event: None, cancel)
    elapsed = time.monotonic() - started
    watcher.join(timeout=1)

    probe = marker.with_suffix(".unlock-probe")
    marker.rename(probe)
    probe.rename(marker)
    assert elapsed < 1.5

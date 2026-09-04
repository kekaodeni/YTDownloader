from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from yt_dlp.downloader.fragment import FragmentFD
from yt_dlp.postprocessor import ffmpeg as ytdlp_ffmpeg

from yt_downloader.core.errors import ErrorContext, OperationCancelled
from yt_downloader.core.models import (
    DownloadRequest,
    FormatOption,
    ProgressTotalSource,
    TaskStatus,
    VideoInfo,
)
from yt_downloader.services.download_service import DownloadService, _interruptible_ytdlp_resources
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


def test_hook_estimate_never_becomes_an_authoritative_progress_denominator(
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
    assert [event.total_bytes for event in transfer] == [None, None]
    assert [event.downloaded_bytes for event in transfer] == [100, 200]
    assert [event.percent for event in transfer] == [None, None]
    assert [event.speed for event in transfer] == [100.0, None]
    assert [event.eta for event in transfer] == [None, None]


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
    assert [event.total_bytes for event in transfer_events] == [None, None, 150, 150]
    assert [event.downloaded_bytes for event in transfer_events] == [50, 100, 150, 150]
    assert [event.percent for event in transfer_events[:2]] == [None, None]
    assert [event.percent for event in transfer_events[2:]] == [100.0, 100.0]
    assert not any(event.total_is_estimate for event in transfer_events)
    assert events[-1].total_bytes == result.file_size
    assert events[-1].total_is_estimate is False
    assert events[0].speed == 2_000_000
    assert events[0].total_source is ProgressTotalSource.UNKNOWN
    assert events[2].total_source is ProgressTotalSource.HOOK_TOTAL_BYTES
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
    marker_path: Path | None = None

    def download(self, _urls: list[str]) -> int:
        marker = Path(self.options["final_path"]).with_suffix(".child-lock")
        type(self).marker_path = marker
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


class FakeYDLWithOwnedPartial(FakeYDL):
    started = threading.Event()
    part_path: Path | None = None

    def download(self, _urls: list[str]) -> int:
        progress = self.options["progress_hooks"][0]
        type(self).part_path = Path(self.options["final_path"]).with_suffix(".part")
        assert type(self).part_path is not None
        with type(self).part_path.open("wb") as handle:
            handle.write(b"partial")
            handle.flush()
            type(self).started.set()
            while True:
                time.sleep(0.01)
                progress({
                    "status": "downloading",
                    "downloaded_bytes": handle.tell(),
                    "total_bytes": 100,
                    "info_dict": {"format_id": "137"},
                })


class FakeYDLWithLeakedFragmentTraceback(FakeYDL):
    """Mimic yt-dlp HLS: cancellation bypasses its destination close call."""

    started = threading.Event()

    def download(self, _urls: list[str]) -> int:
        part_path = Path(self.options["final_path"]).with_suffix(".part")
        handle = part_path.open("wb")
        handle.write(b"fragment")
        handle.flush()
        fragment_context = {"dest_stream": handle}

        def retained_progress_hook() -> object:
            return fragment_context["dest_stream"]

        fragment_context["progress_hook"] = retained_progress_hook
        type(self).started.set()
        time.sleep(0.05)
        self.options["progress_hooks"][0]({
            "status": "downloading",
            "downloaded_bytes": 8,
            "total_bytes_estimate": 8,
            "fragment_index": 1,
            "fragment_count": 2,
            "info_dict": {"format_id": "137"},
        })
        handle.close()
        return 0


def test_user_cancellation_removes_only_the_task_owned_partial_files(
    tmp_path: Path,
) -> None:
    FakeYDLWithOwnedPartial.started = threading.Event()
    FakeYDLWithOwnedPartial.part_path = None
    request = _request(tmp_path)
    unrelated = tmp_path / "keep-me.part"
    unrelated.write_bytes(b"user file")
    cancel = threading.Event()
    service = DownloadService(
        ydl_factory=FakeYDLWithOwnedPartial,
        require_tools=False,
        media_validator=lambda _path: True,
    )

    watcher = threading.Thread(
        target=lambda: (FakeYDLWithOwnedPartial.started.wait(2), cancel.set()),
    )
    watcher.start()
    with pytest.raises(OperationCancelled) as cancelled:
        service.download(request, lambda _event: None, cancel)
    watcher.join(timeout=1)

    assert FakeYDLWithOwnedPartial.part_path is not None
    assert not FakeYDLWithOwnedPartial.part_path.exists()
    assert unrelated.read_bytes() == b"user file"
    assert cancelled.value.cleanup_report is not None
    assert cancelled.value.cleanup_report.succeeded


@pytest.mark.skipif(sys.platform != "win32", reason="Windows holds open files during deletion")
def test_user_cancellation_releases_fragment_handle_retained_by_traceback(
    tmp_path: Path,
) -> None:
    FakeYDLWithLeakedFragmentTraceback.started = threading.Event()
    request = _request(tmp_path)
    cancel = threading.Event()
    service = DownloadService(
        ydl_factory=FakeYDLWithLeakedFragmentTraceback,
        require_tools=False,
        media_validator=lambda _path: True,
    )

    watcher = threading.Thread(
        target=lambda: (FakeYDLWithLeakedFragmentTraceback.started.wait(2), cancel.set()),
    )
    watcher.start()
    with pytest.raises(OperationCancelled) as cancelled:
        service.download(request, lambda _event: None, cancel)
    watcher.join(timeout=1)

    assert cancelled.value.cleanup_report is not None
    assert cancelled.value.cleanup_report.succeeded
    assert not (tmp_path / ".ytdownloader-tmp").exists()


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
    FakeYDLWithFfmpegChild.marker_path = None
    request = _request(tmp_path)
    cancel = threading.Event()
    service = DownloadService(
        ydl_factory=FakeYDLWithFfmpegChild,
        deno_path=tmp_path / "deno.exe",
        ffmpeg_path=tmp_path / "ffmpeg.exe",
        require_tools=False,
        media_validator=lambda _path: True,
    )

    def cancel_after_child_starts() -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            marker = FakeYDLWithFfmpegChild.marker_path
            if marker is not None and marker.exists():
                break
            time.sleep(0.01)
        cancel.set()

    watcher = threading.Thread(target=cancel_after_child_starts)
    watcher.start()
    started = time.monotonic()
    with pytest.raises(OperationCancelled):
        service.download(request, lambda _event: None, cancel)
    elapsed = time.monotonic() - started
    watcher.join(timeout=1)

    marker = FakeYDLWithFfmpegChild.marker_path
    assert marker is not None
    assert not marker.exists()
    assert not (tmp_path / ".ytdownloader-tmp").exists()
    assert elapsed < 1.5


def test_cancel_exception_unwinds_ffmpeg_patch_without_replacing_the_error() -> None:
    cancel = threading.Event()
    context = ErrorContext(stage="Downloading video")

    with pytest.raises(OperationCancelled):
        with _interruptible_ytdlp_resources(cancel, context):
            raise OperationCancelled(context)


def test_cancel_closes_ytdlp_fragment_destination_before_context_restores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cancel = threading.Event()
    context = ErrorContext(stage="Downloading video")
    destination = tmp_path / "fragment.part"

    def leaky_fragment_download(_self, fragment_context, *_args, **_kwargs):
        fragment_context["dest_stream"] = destination.open("wb")
        cancel.set()
        raise OperationCancelled(context)

    monkeypatch.setattr(FragmentFD, "download_and_append_fragments", leaky_fragment_download)
    fragment_context: dict[str, object] = {}

    with pytest.raises(OperationCancelled):
        with _interruptible_ytdlp_resources(cancel, context):
            FragmentFD.download_and_append_fragments(object(), fragment_context, [], {})

    assert fragment_context["dest_stream"].closed is True
    assert FragmentFD.download_and_append_fragments is leaky_fragment_download

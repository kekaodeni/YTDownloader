"""Real yt-dlp downloads from loopback; no YouTube/network availability dependency."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from itertools import count
from pathlib import Path
import subprocess
import threading

import pytest
import yt_dlp

from yt_downloader.core.models import DownloadRequest, FormatOption, TaskStatus, VideoInfo
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.network_policy import NetworkPolicy


@pytest.mark.integration
@pytest.mark.parametrize("delivery", ["hls", "http"])
def test_real_vp9_progress_matches_native_delivery(tmp_path: Path, delivery: str) -> None:
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        pytest.skip("Local FFmpeg is unavailable")
    media = tmp_path / "本地媒体"
    media.mkdir()
    output_args = (
        ["-c:a", "aac", "-f", "hls", "-hls_time", "1", "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4", "sample.m3u8"]
        if delivery == "hls" else ["-c:a", "libopus", "sample.webm"]
    )
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=s=160x90:d=4:r=12",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-shortest", "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
        "-g", "12", *output_args,
    ], cwd=media, check=True, capture_output=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(media)))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/{output_args[-1]}"
        with yt_dlp.YoutubeDL({"quiet": True, "proxy": "", "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        format_id = info["format_id"]
        extension = "mp4" if delivery == "hls" else "webm"
        option = FormatOption("VP9", 90, 12, "vp9", "aac", extension.upper(), extension, format_id, None, False, format_id)
        video = VideoInfo("local-vp9", url, "本地 VP9", "test", 4, None, None, (option,))
        request = DownloadRequest("local", video, option, tmp_path / "下载", "本地 VP9")
        native_events = []

        def native_ydl(options):
            def capture(data):
                native_events.append({key: data.get(key) for key in (
                    "status", "downloaded_bytes", "total_bytes", "total_bytes_estimate",
                    "fragment_index", "speed", "eta",
                )})
            return yt_dlp.YoutubeDL({**options, "progress_hooks": [capture, *options["progress_hooks"]]})

        events = []
        ticks = count()
        result = DownloadService(
            ydl_factory=native_ydl, ffmpeg_path=ffmpeg, require_tools=False,
            network_policy=NetworkPolicy("direct"), clock=lambda: next(ticks) / 10,
        ).download(request, events.append, threading.Event())

        transfer = [event for event in events if event.status == TaskStatus.DOWNLOADING_VIDEO]
        if delivery == "hls":
            estimated = [event for event in transfer if event.total_is_estimate]
            assert estimated, "Native HLS estimates must not be discarded"
            native_estimates = {int(event["total_bytes_estimate"]) for event in native_events if event["total_bytes_estimate"]}
            assert all(event.total_bytes in native_estimates for event in estimated)
            assert any(0 < event.percent < 99 for event in estimated)
        else:
            expected_size = (media / "sample.webm").stat().st_size
            assert all(event.total_bytes == expected_size for event in transfer)
            assert not any(event.total_is_estimate for event in transfer)
            assert any(0 < event.percent < 99 for event in transfer)
            assert [event.percent for event in transfer] == sorted(event.percent for event in transfer)
        assert all(event.percent is None or event.percent < 100 for event in events if event.status == TaskStatus.DOWNLOADING_VIDEO)
        assert events[-1].percent == 100
        assert events[-1].total_bytes == result.file_path.stat().st_size
        assert events[-1].total_is_estimate is False
        assert not (request.output_directory / ".ytdownloader-tmp").exists()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

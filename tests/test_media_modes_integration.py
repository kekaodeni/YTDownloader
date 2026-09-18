"""Real local HTTP downloads and FFmpeg processing; no public content required."""
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import threading

import pytest
import yt_dlp

from test_download_service import _request
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.ffmpeg_service import FfmpegService


@pytest.mark.parametrize('mode,codec', [('video_audio', 'original'), ('video_only', 'original'),
                                      ('audio_only', 'original'), ('audio_only', 'mp3'), ('audio_only', 'flac')])
def test_real_streams_and_audio_processing(tmp_path, mode, codec):
    ffmpeg = find_tool('ffmpeg')
    assert ffmpeg and find_tool('ffprobe'), 'Phase 3 acceptance requires bundled FFmpeg'
    source = tmp_path / 'http'
    source.mkdir()
    subprocess.run([str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'color=s=160x90:d=0.3',
                    '-an', '-c:v', 'libx264', str(source / 'video.mp4')], check=True, capture_output=True)
    subprocess.run([str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.3',
                    '-vn', '-c:a', 'aac', str(source / 'audio.m4a')], check=True, capture_output=True)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(source)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    class LocalYDL(yt_dlp.YoutubeDL):
        def download(self, urls):
            self.process_ie_result({'id': 'test', 'title': 'Test', 'extractor': 'fixture',
                'formats': [
                    {'format_id': '140', 'url': base + '/audio.m4a', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a'},
                    {'format_id': '137', 'url': base + '/video.mp4', 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none'},
                ]}, download=True)
            return 0
    request = replace(_request(tmp_path / 'out'), media_mode=mode, audio_codec=codec)
    try:
        result = DownloadService(ydl_factory=LocalYDL).download(request, lambda event: None, threading.Event())
        assert FfmpegService().has_media_streams(result.file_path, mode)
        if codec in {'mp3', 'flac'}:
            assert result.file_path.suffix == '.' + codec
        assert not list((tmp_path / 'out').glob('.ytd-task-*'))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

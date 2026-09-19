"""Local subtitle transfer, real conversion and stream-copy embedding."""
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import threading

import pytest

from test_download_service import _request
from yt_downloader.core.models import SubtitleTrack
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.subtitle_service import SubtitleService
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.network_policy import NetworkPolicy


@pytest.mark.parametrize('subtitle_format,embed,auto', [('srt', False, False), ('vtt', False, True), ('srt', True, False), ('vtt', True, True)])
def test_real_subtitle_conversion_and_embedding(tmp_path, subtitle_format, embed, auto):
    subtitle = tmp_path / 'input.vtt'
    subtitle.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:00.250\nHello 字幕\n', encoding='utf-8')
    media = tmp_path / 'media.mp4'
    subprocess.run([str(find_tool('ffmpeg')), '-v', 'error', '-f', 'lavfi', '-i', 'color=s=160x90:d=0.3',
                    '-c:v', 'libx264', str(media)], check=True, capture_output=True)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = _request(tmp_path)
    track = SubtitleTrack('en', 'vtt', f'http://127.0.0.1:{server.server_port}/input.vtt', is_auto=auto)
    video = replace(request.video, **({'automatic_captions': (track,)} if auto else {'subtitles': (track,)}))
    request = replace(request, video=video, subtitle_enabled=True, subtitle_auto=auto,
                      subtitle_languages=('en',), subtitle_format=subtitle_format, subtitle_embed=embed)
    try:
        result = SubtitleService(network_policy=NetworkPolicy('direct')).process(request, media, tmp_path, threading.Event())
        assert not result.warnings
        assert result.auto_used is auto
        assert result.embedded is embed
        if embed:
            streams = FfmpegService().probe(result.media)['streams']
            assert any(stream['codec_type'] == 'subtitle' for stream in streams)
            assert next(stream for stream in streams if stream['codec_type'] == 'video')['codec_name'] == 'h264'
        else:
            path = result.files[0][1]
            assert path.suffix == '.' + subtitle_format
            assert 'Hello 字幕' in path.read_text(encoding='utf-8')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

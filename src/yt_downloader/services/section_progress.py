"""Observe yt-dlp's native section FFmpeg process without choosing media inputs."""
from __future__ import annotations

import math
from dataclasses import replace
import re
import subprocess
import threading
import time
from pathlib import Path

from yt_downloader.core.errors import OperationCancelled
from yt_downloader.core.models import DownloadProgress, ProgressTotalSource, TaskStatus
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.section_network import section_process_options


class SectionDownloadProgressAdapter:
    def __init__(self, request, callback, *, log=lambda line: None, clock=time.monotonic):
        self.request, self.callback, self.log, self.clock = request, callback, log, clock
        self.duration = request.clip_end - request.clip_start
        if self.duration <= 0:
            raise ValueError('Section duration must be positive')
        self.fields = {}
        self.latest = None
        self.proxies = None
        self.position = 0.0
        self.previous_bytes = None
        self.previous_at = None
        self.total = None
        if request.video.duration and request.video.duration >= self.duration and request.format.estimated_size:
            self.total = round(request.format.estimated_size * self.duration / request.video.duration)
        self.status = TaskStatus.DOWNLOADING_AUDIO if request.media_mode == 'audio_only' else TaskStatus.DOWNLOADING_VIDEO

    def started(self):
        self.publish(DownloadProgress(self.request.task_id, self.status, 0.0, total_bytes=self.total,
                                      total_is_estimate=self.total is not None,
                                      total_source=ProgressTotalSource.METADATA_FILESIZE_APPROX if self.total else ProgressTotalSource.UNKNOWN))

    def publish(self, progress):
        self.latest = progress
        self.callback(progress)

    def finished(self, data):
        # FFmpegFD's finished hook stats the downloaded section file itself.
        # Full-video metadata totals must not reappear during post-processing.
        size = self.number(data.get('downloaded_bytes'))
        if size is not None:
            self.latest = replace(self.latest, downloaded_bytes=int(size), total_bytes=int(size),
                                  total_is_estimate=False, total_source=ProgressTotalSource.HOOK)

    @staticmethod
    def number(value):
        try:
            value = float(value)
            return value if math.isfinite(value) and value >= 0 else None
        except (TypeError, ValueError):
            return None

    def feed(self, line):
        key, separator, value = line.strip().partition('=')
        if not separator:
            return
        if key != 'progress':
            self.fields[key] = value
            return
        fields, self.fields = self.fields, {}
        raw = self.number(fields.get('out_time_us', fields.get('out_time_ms')))
        seconds = raw / 1_000_000 if raw is not None else None
        if seconds is None:
            stamp = fields.get('out_time', '').split(':')
            if len(stamp) == 3:
                parts = [self.number(part) for part in stamp]
                if all(part is not None for part in parts):
                    seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
        if seconds is None:
            return
        self.position = max(self.position, min(self.duration, seconds))
        factor = self.number(fields.get('speed', '').removesuffix('x'))
        eta = round((self.duration - self.position) / factor) if factor else None
        size = self.number(fields.get('total_size'))
        size = int(size) if size is not None else None
        now, speed = self.clock(), None
        if size is not None and self.previous_bytes is not None and now > self.previous_at:
            speed = max(0, size - self.previous_bytes) / (now - self.previous_at)
        if size is not None:
            self.previous_bytes, self.previous_at = size, now
        self.publish(DownloadProgress(
            self.request.task_id, self.status, self.position * 100 / self.duration, size, self.total,
            speed, eta, total_is_estimate=self.total is not None,
            total_source=ProgressTotalSource.METADATA_FILESIZE_APPROX if self.total else ProgressTotalSource.UNKNOWN))

    def stderr(self, line):
        # Signed media URL query parameters must never reach the error report.
        safe = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[REDACTED]', redact_sensitive(line.rstrip()))
        self.log('FFmpeg: ' + safe)


def observed_section_popen(base, adapter, cancel_event, context):
    """Return a process type only for the active task's FFmpegFD section call.

    The native argv, including input headers/cookies/seek/mapping/mux, stays
    intact. Separate readers drain both pipes so FFmpeg cannot block on stderr.
    Pause follows the existing stop/restart worker contract, not fake suspend.
    """
    class SectionPopen(base):
        def __init__(self, args, *remaining, **kwargs):
            if adapter.proxies is not None:
                args, kwargs['env'] = section_process_options(args, kwargs.get('env'), adapter.proxies)
            # This is an external FFmpeg file download, never a postprocessor.
            args = [*args[:-1], '-progress', 'pipe:1', '-nostats', '-loglevel', 'warning', args[-1]]
            kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            super().__init__(args, *remaining, **kwargs)
            self._stopping = False
            self._read_error = None
            def read(stream, consume):
                try:
                    for line in stream:
                        consume(line.decode('utf-8', 'replace') if isinstance(line, bytes) else line)
                except Exception as error:
                    self._read_error = error
            self._readers = [threading.Thread(target=read, args=(self.stdout, adapter.feed), daemon=True),
                             threading.Thread(target=read, args=(self.stderr, adapter.stderr), daemon=True)]
            try:
                adapter.started()
            except BaseException:
                self._stopping = True
                self.kill(timeout=None)
                raise
            for reader in self._readers:
                reader.start()

        def wait(self, timeout=None):
            if self._stopping or not hasattr(self, '_readers'):
                return super().wait(timeout=timeout)
            deadline = time.monotonic() + timeout if timeout is not None else None
            try:
                while True:
                    if cancel_event.is_set() or self._read_error:
                        self._stopping = True
                        self.kill(timeout=None)
                        if self._read_error:
                            raise self._read_error
                        raise OperationCancelled(context)
                    try:
                        result = super().wait(timeout=.1 if deadline is None else max(0, min(.1, deadline - time.monotonic())))
                        break
                    except subprocess.TimeoutExpired:
                        if deadline is not None and time.monotonic() >= deadline:
                            raise
            finally:
                if self.poll() is not None:
                    for reader in self._readers:
                        reader.join()
            if self._read_error:
                raise self._read_error
            return result
    return SectionPopen


def is_section_ffmpeg(args):
    return (isinstance(args, (list, tuple)) and bool(args)
            and Path(args[0]).stem.lower().startswith('ffmpeg') and '-i' in args and '-t' in args)

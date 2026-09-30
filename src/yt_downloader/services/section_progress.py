"""Observe yt-dlp's native section FFmpeg process without choosing media inputs."""
from __future__ import annotations

import math
from dataclasses import replace
import re
import subprocess
import threading
import time
from pathlib import Path

from yt_downloader.core.errors import AppError, OperationCancelled
from yt_downloader.infrastructure.windows_job import ProcessJob
from yt_downloader.core.models import DownloadProgress, ProgressTotalSource, TaskStatus
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.section_network import section_process_options
from yt_downloader.services.download_speed import DownloadSpeedEstimator


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
        self.eta = None
        self.speed_estimator = DownloadSpeedEstimator(clock=clock)
        self.output_path = None
        self.last_publish_at = float('-inf')
        self.lock = threading.RLock()
        self.last_size = None
        self.input_error = ''
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
        self.last_publish_at = self.clock()

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
        with self.lock:
            self._feed(line)

    def _feed(self, line):
        key, separator, value = line.strip().partition('=')
        if not separator:
            return
        if key != 'progress':
            self.fields[key] = value
            return
        fields, self.fields = self.fields, {}
        if self.speed_estimator.paused_at is not None:
            return
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
        self.eta = eta
        size = self.number(fields.get('total_size'))
        size = int(size) if size is not None else None
        if size is None and self.output_path is not None:
            try:
                size = self.output_path.stat().st_size
            except OSError:
                pass
        now = self.clock()
        # A file-stat tick may precede an older buffered FFmpeg progress block.
        # Both sources observe one growing output; never reset its byte counter.
        if size is not None and self.last_size is not None:
            size = max(size, self.last_size)
        self.last_size = size
        speed = self.speed_estimator.sample(size)
        if now - self.last_publish_at < .5 and value != 'end':
            return
        self.publish(DownloadProgress(
            self.request.task_id, self.status, self.position * 100 / self.duration, size, self.total,
            speed, eta, total_is_estimate=self.total is not None,
            total_source=ProgressTotalSource.METADATA_FILESIZE_APPROX if self.total else ProgressTotalSource.UNKNOWN))

    def tick(self):
        with self.lock:
            if self.latest is None or self.speed_estimator.paused_at is not None or self.clock() - self.last_publish_at < .5:
                return
            size = self.last_size
            if self.output_path is not None:
                try:
                    size = max(size or 0, self.output_path.stat().st_size)
                except OSError:
                    pass
            self.last_size = size
            speed = self.speed_estimator.sample(size)
            # A pipe block can arrive just before the 500ms publish boundary.
            # Keep its media position even when that block was rate limited.
            self.publish(replace(self.latest, percent=self.position * 100 / self.duration,
                                 downloaded_bytes=size, speed=speed, eta=self.eta))

    def stderr(self, line):
        # Signed media URL query parameters must never reach the error report.
        safe = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[REDACTED]', redact_sensitive(line.rstrip()))
        self.log('FFmpeg: ' + safe)
        # FFmpeg can exit with code zero after one input dies while the other
        # continues. Do not deliver a section containing only a partial video.
        if re.search(r'Unable to read from socket|Error during demuxing: (?:I/O error|Connection|End of file)',
                     safe, re.IGNORECASE):
            self.input_error = safe


def observed_section_popen(base, adapter, cancel_event, context):
    """Return a process type only for the active task's FFmpegFD section call.

    The native argv, including input headers/cookies/seek/mapping/mux, stays
    intact. Separate readers drain both pipes so FFmpeg cannot block on stderr.
    Clip pause suspends the same job tree; normal download control stays native.
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
            adapter.output_path = Path(args[-1].removeprefix('file:'))
            self._job = None
            self._suspended = False
            if getattr(cancel_event, 'live_pause', False):
                self._job = ProcessJob()
                if not self._job.assign(self.pid):
                    self._stopping = True
                    self.kill(timeout=None)
                    self._job.close()
                    raise AppError('ffmpeg_failed', 'FFmpeg 处理视频失败。',
                                   'Unable to contain the section process for pause/resume', context)
                cancel_event.section_pid = self.pid
                cancel_event.section_path = adapter.output_path
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
                if self._job:
                    self._job.close()
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
                        if self._job:
                            self._job.terminate()
                        self.kill(timeout=None)
                        if self._read_error:
                            raise self._read_error
                        raise OperationCancelled(context)
                    if adapter.input_error:
                        self._stopping = True
                        if self._job:
                            self._job.terminate()
                        if self.poll() is None:
                            self.kill(timeout=None)
                        raise AppError('NETWORK_ERROR', '网络连接失败，请检查网络或代理后重试。',
                                       adapter.input_error, context)
                    if self._job:
                        paused = cancel_event.is_paused()
                        if paused != self._suspended:
                            with adapter.lock:
                                try:
                                    if paused:
                                        self._job.suspend()
                                        adapter.speed_estimator.pause()
                                        stage = TaskStatus.PAUSED
                                    else:
                                        self._job.resume()
                                        adapter.speed_estimator.resume()
                                        stage = adapter.status
                                except OSError as error:
                                    self._stopping = True
                                    self._job.terminate()
                                    self.kill(timeout=None)
                                    raise AppError('ffmpeg_failed', 'FFmpeg 处理视频失败。',
                                                   str(error), context) from None
                                self._suspended = paused
                                adapter.publish(replace(adapter.latest, status=stage, speed=None, eta=None))
                    adapter.tick()
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
            if adapter.input_error:
                raise AppError('NETWORK_ERROR', '网络连接失败，请检查网络或代理后重试。',
                               adapter.input_error, context)
            return result

        def __exit__(self, *args):
            try:
                return super().__exit__(*args)
            finally:
                if self._job:
                    self._job.close()
    return SectionPopen


def is_section_ffmpeg(args):
    return (isinstance(args, (list, tuple)) and bool(args)
            and Path(args[0]).stem.lower().startswith('ffmpeg') and '-i' in args and '-t' in args)

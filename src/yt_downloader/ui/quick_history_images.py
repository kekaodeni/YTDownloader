"""Read-only, asynchronous video thumbnails for history presentation."""
from collections import OrderedDict
import hashlib
import logging
import os
from pathlib import Path
import threading
import uuid
from PySide6.QtCore import QObject, QThreadPool, Signal, QUrl, Qt
from PySide6.QtGui import QImage
from yt_downloader.workers.function_worker import FunctionWorker

logger = logging.getLogger(__name__)


def media_key(path):
    path = Path(path)
    info = path.stat()
    return hashlib.sha256(f'cover-v2|{path.resolve()}|{info.st_mtime_ns}|{info.st_size}'.encode('utf-8')).hexdigest()


def render_thumbnail(ffmpeg, media, directory, key, cancel):
    """Prefer embedded cover; otherwise decode a real video frame. Never write media."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{key}.jpg'
    if destination.is_file():
        return destination
    probe = ffmpeg.probe(media, cancel_event=cancel)
    # Matroska exposes WebP (and other image attachments) as `attachment`,
    # rather than the attached_pic video stream used by PNG/JPEG covers.
    attachment = next((s for s in probe.get('streams', [])
                       if s.get('codec_type') == 'attachment'
                       and str(s.get('tags', {}).get('filename', '')).startswith('cover.')
                       and str(s.get('tags', {}).get('mimetype', '')).startswith('image/')), None)
    streams = [s for s in probe.get('streams', []) if s.get('codec_type') == 'video']
    if not streams:
        raise ValueError('No video stream available for history thumbnail')
    stream = next((s for s in streams if ffmpeg._is_cover_stream(s)), next((s for s in streams if not s.get('disposition', {}).get('attached_pic')), streams[0]))
    temporary = directory / f'{key}.{uuid.uuid4().hex}.tmp.jpg'
    attached_image = temporary.with_suffix('.cover')
    arguments = [str(ffmpeg.ffmpeg_path), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y']
    if not stream.get('disposition', {}).get('attached_pic'):
        duration = float(probe.get('format', {}).get('duration') or 0)
        if duration > 2:
            arguments += ['-ss', '1']
    arguments += ['-i', str(media), '-map', f"0:{stream['index']}", '-frames:v', '1',
                  '-vf', 'scale=360:360:force_original_aspect_ratio=decrease', '-q:v', '3', str(temporary)]
    try:
        if attachment:
            ffmpeg._run([str(ffmpeg.ffmpeg_path), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                         f'-dump_attachment:{attachment["index"]}', str(attached_image),
                         '-i', str(media), '-map', '0:V:0', '-frames:v', '1', '-f', 'null', os.devnull],
                        cancel_event=cancel, timeout=30, stage='History thumbnail')
            image = QImage(str(attached_image))
            if image.isNull() or not image.scaled(360, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(str(temporary), 'JPEG', 90):
                raise ValueError('Embedded cover cannot be decoded')
        else:
            ffmpeg._run(arguments, cancel_event=cancel, timeout=30, stage='History thumbnail')
        if not temporary.is_file() or not temporary.stat().st_size:
            raise ValueError('Empty history thumbnail')
        if media_key(media) != key:
            return None
        temporary.replace(destination)
        files = sorted(directory.glob('*.jpg'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for old in files[256:]:
            if len(old.stem) == 64 and all(c in '0123456789abcdef' for c in old.stem):
                old.unlink(missing_ok=True)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
        attached_image.unlink(missing_ok=True)


class HistoryImageCache(QObject):
    ready = Signal(str, str, str)

    def __init__(self, ffmpeg, directory, parent=None):
        super().__init__(parent)
        self.ffmpeg = ffmpeg
        self.directory = Path(directory)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.cancel = threading.Event()
        self._workers = {}
        self._requested = OrderedDict()
        self._pending = OrderedDict()

    def request(self, task_id, media):
        if self.cancel.is_set() or not self.ffmpeg.available:
            return
        try:
            key = media_key(media)
        except OSError:
            return
        token = (task_id, key)
        if token in self._requested:
            return
        self._pending[token] = Path(media)
        self._pending.move_to_end(token)
        while len(self._pending) > 32:
            self._pending.popitem(last=False)
        self._drain()

    def _drain(self):
        if self.cancel.is_set() or self._workers or not self._pending:
            return
        token, media = self._pending.popitem(last=True)
        task_id, key = token
        self._requested[token] = True
        while len(self._requested) > 512:
            self._requested.popitem(last=False)
        worker = FunctionWorker(render_thumbnail, self.ffmpeg, Path(media), self.directory, key, self.cancel)
        self._workers[token] = worker
        worker.signals.result.connect(lambda path, t=task_id, k=key: self._ready(t, k, path))
        worker.signals.error.connect(lambda error: logger.warning('History thumbnail unavailable: %s', error.technical_message))
        worker.signals.finished.connect(lambda t=token: self._finished(t))
        self.pool.start(worker)

    def _finished(self, token):
        self._workers.pop(token, None)
        self._drain()

    def _ready(self, task_id, key, path):
        if path and not self.cancel.is_set():
            self.ready.emit(task_id, key, QUrl.fromLocalFile(str(path)).toString())

    def invalidate(self, task_id):
        for token in tuple(self._requested):
            if token[0] == task_id:
                self._requested.pop(token, None)

    def close(self):
        self.cancel.set()
        self._pending.clear()
        self.pool.clear()
        self.pool.waitForDone()
        self._workers.clear()

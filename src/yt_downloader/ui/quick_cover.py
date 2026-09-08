"""Mechanical migration of the cover dialog's existing worker coordination."""
from pathlib import Path
import threading

from PySide6.QtCore import QThreadPool, Signal, Slot, QUrl
from PySide6.QtGui import QImageReader, QDesktopServices

from yt_downloader.core.errors import AppError
from yt_downloader.services.ffmpeg_service import FfmpegService, ExplorerCoverStatus
from yt_downloader.core.formatting import format_duration
from yt_downloader.ui.quick_dialogs import DialogSession
from yt_downloader.workers.function_worker import FunctionWorker


class CoverSession(DialogSession):
    thumbnail_set = Signal(object)
    error = Signal(object)

    def __init__(self, media_path, video_id, output_directory, ffmpeg, parent):
        super().__init__(parent.dialogs, kind='cover', title='设置视频封面',
                         duration=0.0, durationText='正在读取视频时长……', timestamp=0.0,
                         preview='', previewRatio=16 / 9, previewText='选择时间后点击“预览”', previewEnabled=False,
                         applyEnabled=False, controlsEnabled=True, completed=False, explorerNeedsSupport=False)
        self._save_copy = not FfmpegService.supports_embedded_cover(media_path)
        self.update(applyText='另存为 MKV 并写入封面' if self._save_copy else '写入视频封面')
        self.update(message='此格式不能直接内嵌封面。将另存为 MKV，不重新编码，保留原文件；历史记录改为打开新副本。' if self._save_copy else '预览图片只用于写入视频，关闭窗口后会自动清理。')
        self.media_path = media_path
        self.video_id = video_id
        self.output_directory = output_directory
        self.ffmpeg = ffmpeg
        self.images = parent.images
        self.duration = 0.0
        self.preview_path = output_directory / f'.{video_id}.preview.jpg'
        self._workers = []
        self._apply_cancel = threading.Event()
        self._reject_pending = False
        self._applying = False
        self._completed = False
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._run(self.ffmpeg.probe_duration, self.media_path, cancel_event=self._apply_cancel, on_result=self._duration_ready)

    def _run(self, function, *args, on_result, **kwargs):
        worker = FunctionWorker(function, *args, **kwargs)
        self._workers.append(worker)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error)
        worker.signals.finished.connect(lambda w=worker: self._worker_finished(w))
        QThreadPool.globalInstance().start(worker)

    def _worker_finished(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        if self._reject_pending and not self._workers:
            self.preview_path.unlink(missing_ok=True)
            self.close()

    def _duration_ready(self, duration):
        if self._apply_cancel.is_set():
            return
        self.duration = duration
        self.update(duration=duration, durationText=f'视频时长：{format_duration(duration)}', previewEnabled=True)

    @Slot(float)
    def setTimestamp(self, seconds):
        if self._state['controlsEnabled']:
            self.update(timestamp=max(0.0, min(self.duration, round(seconds, 1))))

    @Slot()
    def generatePreview(self):
        if not self._state['previewEnabled']:
            return
        self.update(previewEnabled=False, preview='', previewRatio=16 / 9, previewText='正在生成预览……')
        worker = FunctionWorker(self.ffmpeg.extract_frame, self.media_path, self._state['timestamp'],
                                self.preview_path, duration=self.duration, cancel_event=self._apply_cancel)
        self._workers.append(worker)
        worker.signals.result.connect(self._preview_ready)
        worker.signals.error.connect(self.error)
        worker.signals.finished.connect(lambda w=worker: self._worker_finished(w))
        worker.signals.finished.connect(lambda: self.update(previewEnabled=True))
        QThreadPool.globalInstance().start(worker)

    def _preview_ready(self, path):
        if self._apply_cancel.is_set():
            path.unlink(missing_ok=True)
            return
        source = self.images.add(Path(path).read_bytes())
        size = QImageReader(str(path)).size()
        ratio = size.width() / size.height() if size.height() > 0 else 16 / 9
        self.update(preview=source, previewRatio=ratio, applyEnabled=bool(source))

    @Slot()
    def apply(self):
        if not self._state['applyEnabled'] or self._applying or self._completed:
            return
        if not self.preview_path.is_file():
            self.error.emit(AppError('thumbnail_missing', '请先生成缩略图预览。', 'Preview file is missing'))
            return
        self._applying = True
        self._apply_cancel.clear()
        self.update(message='正在无损写入封面并验证视频结构……', previewEnabled=False,
                    applyEnabled=False, controlsEnabled=False)
        options = {}
        if self._save_copy:
            destination = self.media_path.with_name(f'{self.media_path.stem} (封面).mkv')
            number = 2
            while destination.exists():
                destination = self.media_path.with_name(f'{self.media_path.stem} (封面 {number}).mkv')
                number += 1
            options['output_path'] = destination
        worker = FunctionWorker(self.ffmpeg.embed_cover, self.media_path, self.preview_path, cancel_event=self._apply_cancel, **options)
        self._workers.append(worker)
        worker.signals.result.connect(self._cover_ready)
        worker.signals.error.connect(self._cover_failed)
        worker.signals.cancelled.connect(self._cover_cancelled)
        worker.signals.finished.connect(lambda w=worker: self._worker_finished(w))
        QThreadPool.globalInstance().start(worker)

    def _cover_ready(self, result):
        self._applying = False
        self._completed = True
        self.preview_path.unlink(missing_ok=True)
        self.update(message=result.message, completed=True, explorerNeedsSupport=result.explorer_status is not ExplorerCoverStatus.MATCHED)
        self.thumbnail_set.emit(result)

    @Slot()
    def openExplorerSupport(self):
        QDesktopServices.openUrl(QUrl('https://github.com/Xanashi/Icaros#installationactivation'))

    def _cover_failed(self, error):
        self._applying = False
        self.update(message='封面写入失败，原视频没有改变。', previewEnabled=True,
                    applyEnabled=self.preview_path.is_file(), controlsEnabled=True)
        self.error.emit(error)

    def _cover_cancelled(self):
        self._applying = False
        self.update(message='封面写入已取消，原视频没有改变。')

    @Slot()
    def reject(self):
        if self._workers:
            self._reject_pending = True
            self._apply_cancel.set()
            self.update(message='正在取消后台操作并清理临时文件……', closeEnabled=False)
            return
        self.preview_path.unlink(missing_ok=True)
        super().reject()

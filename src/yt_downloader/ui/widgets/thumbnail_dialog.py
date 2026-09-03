from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from yt_downloader.core.errors import AppError
from yt_downloader.core.formatting import format_duration
from yt_downloader.services.ffmpeg_service import CoverEmbedResult, FfmpegService
from yt_downloader.ui.localization import localize_dialog_button_box
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree
from yt_downloader.workers.function_worker import FunctionWorker


class ThumbnailDialog(QDialog):
    thumbnail_set = Signal(object)
    error = Signal(object)

    def __init__(self, media_path: Path, video_id: str, output_directory: Path, ffmpeg: FfmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.media_path = media_path
        self.video_id = video_id
        self.output_directory = output_directory
        self.ffmpeg = ffmpeg
        self.duration = 0.0
        self.preview_path = output_directory / f".{video_id}.preview.jpg"
        self._workers: list[FunctionWorker] = []
        self._apply_cancel = threading.Event()
        self._reject_pending = False
        self._applying = False
        self._completed = False
        self.setWindowTitle("更换缩略图")
        self.resize(620, 470)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        title = QLabel("选择视频中的一个时间点")
        apply_typography(title, FontRole.SECTION_TITLE)
        root.addWidget(title)
        self.duration_label = QLabel("正在读取视频时长……")
        apply_typography(self.duration_label, FontRole.SECONDARY)
        root.addWidget(self.duration_label)
        self.result_label = QLabel("预览图片只用于写入视频，关闭窗口后会自动清理。")
        apply_typography(self.result_label, FontRole.SECONDARY)
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)
        self.preview = QLabel("选择时间后点击“预览”")
        self.preview.setProperty("fluentRole", "subtle")
        self.preview.setMinimumHeight(280)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.preview, 1)
        time_row = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(0, 0)
        self.spin.setDecimals(1)
        self.spin.setSuffix(" 秒")
        self.slider.valueChanged.connect(lambda value: self.spin.setValue(float(value)))
        self.spin.valueChanged.connect(lambda value: self.slider.setValue(round(value)))
        time_row.addWidget(self.slider, 1)
        time_row.addWidget(self.spin)
        root.addLayout(time_row)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        localize_dialog_button_box(actions)
        actions.rejected.connect(self.reject)
        self.close_button = actions.button(QDialogButtonBox.StandardButton.Cancel)
        self.preview_button = QPushButton("预览")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self._generate_preview)
        self.apply_button = QPushButton("写入视频封面")
        self.apply_button.setProperty("fluentAppearance", "primary")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply)
        actions.addButton(self.preview_button, QDialogButtonBox.ButtonRole.ActionRole)
        actions.addButton(self.apply_button, QDialogButtonBox.ButtonRole.AcceptRole)
        root.addWidget(actions)
        apply_typography_tree(self)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._run(
            self.ffmpeg.probe_duration,
            self.media_path,
            cancel_event=self._apply_cancel,
            on_result=self._duration_ready,
        )

    def _run(self, function, *args, on_result, **kwargs) -> None:
        worker = FunctionWorker(function, *args, **kwargs)
        self._workers.append(worker)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error)
        worker.signals.finished.connect(lambda w=worker: self._worker_finished(w))
        QThreadPool.globalInstance().start(worker)

    def _worker_finished(self, worker: FunctionWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        if self._reject_pending and not self._workers:
            self.preview_path.unlink(missing_ok=True)
            QDialog.reject(self)

    def _duration_ready(self, duration: float) -> None:
        if self._apply_cancel.is_set():
            return
        self.duration = duration
        maximum = max(0, int(duration))
        self.slider.setRange(0, maximum)
        self.spin.setRange(0, duration)
        self.duration_label.setText(f"视频时长：{format_duration(duration)}")
        self.preview_button.setEnabled(True)

    def _generate_preview(self) -> None:
        self.preview_button.setEnabled(False)
        self.preview.setText("正在生成预览……")
        worker = FunctionWorker(
            self.ffmpeg.extract_frame,
            self.media_path,
            self.spin.value(),
            self.preview_path,
            duration=self.duration,
            cancel_event=self._apply_cancel,
        )
        self._workers.append(worker)
        worker.signals.result.connect(self._preview_ready)
        worker.signals.error.connect(self.error)
        worker.signals.finished.connect(lambda w=worker: self._worker_finished(w))
        worker.signals.finished.connect(lambda: self.preview_button.setEnabled(True))
        QThreadPool.globalInstance().start(worker)

    def _preview_ready(self, path: Path) -> None:
        if self._apply_cancel.is_set():
            path.unlink(missing_ok=True)
            return
        pixmap = QPixmap(str(path))
        self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.apply_button.setEnabled(not pixmap.isNull())

    def _apply(self) -> None:
        if not self.preview_path.is_file():
            self.error.emit(AppError("thumbnail_missing", "请先生成缩略图预览。", "Preview file is missing"))
            return
        self._applying = True
        self._apply_cancel.clear()
        self.result_label.setText("正在无损写入封面并验证视频结构……")
        self.preview_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.slider.setEnabled(False)
        self.spin.setEnabled(False)
        worker = FunctionWorker(
            self.ffmpeg.embed_cover,
            self.media_path,
            self.preview_path,
            cancel_event=self._apply_cancel,
        )
        self._workers.append(worker)
        worker.signals.result.connect(self._cover_ready)
        worker.signals.error.connect(self._cover_failed)
        worker.signals.cancelled.connect(self._cover_cancelled)
        worker.signals.finished.connect(lambda w=worker: self._worker_finished(w))
        QThreadPool.globalInstance().start(worker)

    def _cover_ready(self, result: CoverEmbedResult) -> None:
        self._applying = False
        self._completed = True
        self.preview_path.unlink(missing_ok=True)
        self.result_label.setText(result.message)
        self.apply_button.hide()
        self.preview_button.hide()
        self.close_button.setText("关闭")
        self.thumbnail_set.emit(result)

    def _cover_failed(self, error: AppError) -> None:
        self._applying = False
        self.result_label.setText("封面写入失败，原视频没有改变。")
        self.preview_button.setEnabled(True)
        self.apply_button.setEnabled(self.preview_path.is_file())
        self.slider.setEnabled(True)
        self.spin.setEnabled(True)
        self.error.emit(error)

    def _cover_cancelled(self) -> None:
        self._applying = False
        self.result_label.setText("封面写入已取消，原视频没有改变。")

    def reject(self) -> None:
        if self._workers:
            self._reject_pending = True
            self._apply_cancel.set()
            self.result_label.setText("正在取消后台操作并清理临时文件……")
            self.close_button.setEnabled(False)
            return
        self.preview_path.unlink(missing_ok=True)
        super().reject()

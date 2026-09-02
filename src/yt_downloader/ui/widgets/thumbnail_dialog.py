from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from yt_downloader.core.errors import AppError
from yt_downloader.core.formatting import format_duration
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.workers.function_worker import FunctionWorker


class ThumbnailDialog(QDialog):
    thumbnail_set = Signal(str)
    error = Signal(object)

    def __init__(self, media_path: Path, video_id: str, output_directory: Path, ffmpeg: FfmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.media_path = media_path
        self.video_id = video_id
        self.output_directory = output_directory
        self.ffmpeg = ffmpeg
        self.duration = 0.0
        self.preview_path = output_directory / f".{video_id}.preview.jpg"
        self.final_path = output_directory / f"{video_id}.jpg"
        self._workers: list[FunctionWorker] = []
        self.setWindowTitle("更换缩略图")
        self.resize(620, 470)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        title = QLabel("选择视频中的一个时间点")
        title.setProperty("headingLevel", "2")
        root.addWidget(title)
        self.duration_label = QLabel("正在读取视频时长……")
        self.duration_label.setProperty("secondary", True)
        root.addWidget(self.duration_label)
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
        actions.rejected.connect(self.reject)
        self.preview_button = QPushButton("预览")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self._generate_preview)
        self.apply_button = QPushButton("设为缩略图")
        self.apply_button.setProperty("fluentAppearance", "primary")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply)
        actions.addButton(self.preview_button, QDialogButtonBox.ButtonRole.ActionRole)
        actions.addButton(self.apply_button, QDialogButtonBox.ButtonRole.AcceptRole)
        root.addWidget(actions)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._run(self.ffmpeg.probe_duration, self.media_path, on_result=self._duration_ready)

    def _run(self, function, *args, on_result) -> None:
        worker = FunctionWorker(function, *args)
        self._workers.append(worker)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error)
        worker.signals.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        QThreadPool.globalInstance().start(worker)

    def _duration_ready(self, duration: float) -> None:
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
        )
        self._workers.append(worker)
        worker.signals.result.connect(self._preview_ready)
        worker.signals.error.connect(self.error)
        worker.signals.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        worker.signals.finished.connect(lambda: self.preview_button.setEnabled(True))
        QThreadPool.globalInstance().start(worker)

    def _preview_ready(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.apply_button.setEnabled(not pixmap.isNull())

    def _apply(self) -> None:
        if not self.preview_path.is_file():
            self.error.emit(AppError("thumbnail_missing", "请先生成缩略图预览。", "Preview file is missing"))
            return
        os.replace(self.preview_path, self.final_path)
        self.thumbnail_set.emit(str(self.final_path))
        self.accept()

    def reject(self) -> None:
        self.preview_path.unlink(missing_ok=True)
        super().reject()


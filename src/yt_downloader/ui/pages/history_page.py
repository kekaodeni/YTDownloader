from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListView, QPushButton, QVBoxLayout, QWidget

from yt_downloader.core.formatting import format_bytes
from yt_downloader.core.models import HistoryRecord, STATUS_TEXT


class HistoryListModel(QAbstractListModel):
    RecordRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, records: list[HistoryRecord] | None = None) -> None:
        super().__init__()
        self.records = records or []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.records)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        record = self.records[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            size = format_bytes(record.file_size)
            return f"{record.title}\n{record.quality_label}  ·  {size}  ·  {STATUS_TEXT[record.status]}"
        if role == Qt.ItemDataRole.DecorationRole and record.thumbnail_path and record.thumbnail_path.is_file():
            return QIcon(str(record.thumbnail_path))
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(100, 72)
        if role == self.RecordRole:
            return record
        return None

    def replace(self, records: list[HistoryRecord]) -> None:
        self.beginResetModel()
        self.records = records
        self.endResetModel()


class HistoryPage(QWidget):
    open_file_requested = Signal(str)
    open_folder_requested = Signal(str)
    copy_link_requested = Signal(str)
    thumbnail_requested = Signal(object)
    retry_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)
        heading = QLabel("历史记录")
        heading.setProperty("headingLevel", "1")
        root.addWidget(heading)
        subtitle = QLabel("仅显示通过本软件下载或中断的任务。")
        subtitle.setProperty("secondary", True)
        root.addWidget(subtitle)
        self.model = HistoryListModel()
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setAlternatingRowColors(False)
        self.list_view.setAccessibleName("下载历史记录")
        self.list_view.selectionModel().selectionChanged.connect(self._selection_changed)
        root.addWidget(self.list_view, 1)
        actions = QHBoxLayout()
        self.open_button = QPushButton("打开文件")
        self.folder_button = QPushButton("打开文件夹")
        self.copy_button = QPushButton("复制链接")
        self.thumbnail_button = QPushButton("更换缩略图")
        self.retry_button = QPushButton("重试")
        for button in (self.open_button, self.folder_button, self.copy_button, self.thumbnail_button, self.retry_button):
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch()
        root.addLayout(actions)
        self.open_button.clicked.connect(lambda: self._with_record(lambda r: self.open_file_requested.emit(str(r.file_path))))
        self.folder_button.clicked.connect(lambda: self._with_record(lambda r: self.open_folder_requested.emit(str(r.file_path))))
        self.copy_button.clicked.connect(lambda: self._with_record(lambda r: self.copy_link_requested.emit(r.url)))
        self.thumbnail_button.clicked.connect(lambda: self._with_record(self.thumbnail_requested.emit))
        self.retry_button.clicked.connect(lambda: self._with_record(self.retry_requested.emit))

    def set_records(self, records: list[HistoryRecord]) -> None:
        self.model.replace(records)
        self._selection_changed()

    def selected_record(self) -> HistoryRecord | None:
        indexes = self.list_view.selectedIndexes()
        return indexes[0].data(HistoryListModel.RecordRole) if indexes else None

    def _with_record(self, action) -> None:
        record = self.selected_record()
        if record:
            action(record)

    def _selection_changed(self, *_args) -> None:
        record = self.selected_record()
        enabled = record is not None
        self.copy_button.setEnabled(enabled)
        file_exists = bool(record and record.file_path.is_file())
        self.open_button.setEnabled(file_exists)
        self.folder_button.setEnabled(file_exists)
        self.thumbnail_button.setEnabled(file_exists and bool(record))
        self.retry_button.setEnabled(enabled)

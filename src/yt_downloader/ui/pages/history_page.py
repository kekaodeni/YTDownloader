from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListView, QMenu, QPushButton, QVBoxLayout, QWidget

from yt_downloader.core.formatting import format_bytes
from yt_downloader.core.models import HistoryRecord, STATUS_TEXT
from yt_downloader.core.models import TaskStatus
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree
from yt_downloader.ui.widgets.confirm_dialog import DeleteHistoryDialog


_TERMINAL_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


class HistoryListView(QListView):
    context_menu_key_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        menu_key = event.key() == Qt.Key.Key_Menu
        shift_f10 = event.key() == Qt.Key.Key_F10 and bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if menu_key or shift_f10:
            self.context_menu_key_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


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
    delete_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)
        heading = QLabel("历史记录")
        apply_typography(heading, FontRole.PAGE_TITLE)
        root.addWidget(heading)
        subtitle = QLabel("仅显示通过本软件下载或中断的任务。")
        apply_typography(subtitle, FontRole.SECONDARY)
        root.addWidget(subtitle)
        self.model = HistoryListModel()
        self.list_view = HistoryListView()
        self.list_view.setModel(self.model)
        self.list_view.setAlternatingRowColors(False)
        self.list_view.setAccessibleName("下载历史记录")
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        self.list_view.context_menu_key_requested.connect(self._show_keyboard_context_menu)
        self.list_view.selectionModel().selectionChanged.connect(self._selection_changed)
        root.addWidget(self.list_view, 1)
        actions = QHBoxLayout()
        self.open_button = QPushButton("打开文件")
        self.folder_button = QPushButton("打开文件夹")
        self.copy_button = QPushButton("复制链接")
        self.thumbnail_button = QPushButton("设置视频封面")
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
        apply_typography_tree(self)

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

    def _record_for_context_position(self, position: QPoint) -> HistoryRecord | None:
        index = self.list_view.indexAt(position) if position.x() >= 0 and position.y() >= 0 else QModelIndex()
        if index.isValid():
            self.list_view.selectionModel().setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
            )
        else:
            index = self.list_view.currentIndex()
        return index.data(HistoryListModel.RecordRole) if index.isValid() else None

    def _show_context_menu(self, position: QPoint) -> None:
        record = self._record_for_context_position(position)
        if record is None:
            return
        menu = self._build_context_menu(record)
        global_position = self.list_view.viewport().mapToGlobal(position)
        self._exec_context_menu(menu, global_position)

    def _show_keyboard_context_menu(self) -> None:
        index = self.list_view.currentIndex()
        if not index.isValid():
            return
        record = index.data(HistoryListModel.RecordRole)
        if record is None:
            return
        menu = self._build_context_menu(record)
        position = self.list_view.visualRect(index).center()
        self._exec_context_menu(menu, self.list_view.viewport().mapToGlobal(position))

    def _exec_context_menu(self, menu: QMenu, global_position: QPoint) -> None:
        menu.exec(global_position)

    def _build_context_menu(self, record: HistoryRecord) -> QMenu:
        menu = QMenu(self)
        file_exists = record.file_path.is_file()
        open_action = menu.addAction("打开文件", lambda: self.open_file_requested.emit(str(record.file_path)))
        folder_action = menu.addAction("打开文件夹", lambda: self.open_folder_requested.emit(str(record.file_path)))
        menu.addAction("复制链接", lambda: self.copy_link_requested.emit(record.url))
        menu.addAction("重新下载", lambda: self.retry_requested.emit(record))
        cover_action = menu.addAction("设置视频封面", lambda: self.thumbnail_requested.emit(record))
        menu.addSeparator()
        delete_action = menu.addAction("删除记录", lambda: self._delete_record(record))
        open_action.setEnabled(file_exists)
        folder_action.setEnabled(file_exists)
        cover_action.setEnabled(file_exists)
        delete_action.setEnabled(record.status in _TERMINAL_STATUSES)
        delete_action.setToolTip("只删除历史记录，不删除视频文件")
        return menu

    def _delete_record(self, record: HistoryRecord) -> None:
        if record.status not in _TERMINAL_STATUSES:
            return
        if self._confirm_delete_record(record):
            self.delete_requested.emit(record)

    def _confirm_delete_record(self, record: HistoryRecord) -> bool:
        return DeleteHistoryDialog(record.title, self).exec() == QDialog.DialogCode.Accepted

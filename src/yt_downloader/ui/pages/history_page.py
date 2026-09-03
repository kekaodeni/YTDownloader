from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListView, QMenu, QPushButton, QVBoxLayout, QWidget

from yt_downloader.core.formatting import format_bytes
from yt_downloader.core.models import HistoryRecord, STATUS_TEXT
from yt_downloader.core.models import TaskStatus
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree
from yt_downloader.ui.widgets.confirm_dialog import DeleteHistoryBatchDialog, DeleteHistoryDialog


_TERMINAL_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


class HistoryListView(QListView):
    context_menu_key_requested = Signal()
    toggle_current_requested = Signal()
    select_all_checked_requested = Signal()
    delete_checked_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.management_mode = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.management_mode:
            if event.key() == Qt.Key.Key_Space:
                self.toggle_current_requested.emit()
                event.accept()
                return
            if event.matches(QKeySequence.StandardKey.SelectAll):
                self.select_all_checked_requested.emit()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Delete:
                self.delete_checked_requested.emit()
                event.accept()
                return
        menu_key = event.key() == Qt.Key.Key_Menu
        shift_f10 = event.key() == Qt.Key.Key_F10 and bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if menu_key or shift_f10:
            self.context_menu_key_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class HistoryListModel(QAbstractListModel):
    RecordRole = Qt.ItemDataRole.UserRole + 1
    checked_changed = Signal(int)

    def __init__(self, records: list[HistoryRecord] | None = None) -> None:
        super().__init__()
        self.records = records or []
        self.management_mode = False
        self._checked_task_ids: set[str] = set()

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
        if role == Qt.ItemDataRole.CheckStateRole and self.management_mode and record.status in _TERMINAL_STATUSES:
            return Qt.CheckState.Checked if record.task_id in self._checked_task_ids else Qt.CheckState.Unchecked
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index)
        if index.isValid() and self.management_mode:
            record = self.records[index.row()]
            if record.status in _TERMINAL_STATUSES:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if (
            role != Qt.ItemDataRole.CheckStateRole
            or not self.management_mode
            or not index.isValid()
        ):
            return False
        record = self.records[index.row()]
        if record.status not in _TERMINAL_STATUSES:
            return False
        if Qt.CheckState(value) is Qt.CheckState.Checked:
            self._checked_task_ids.add(record.task_id)
        else:
            self._checked_task_ids.discard(record.task_id)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.checked_changed.emit(len(self._checked_task_ids))
        return True

    def replace(self, records: list[HistoryRecord]) -> None:
        self.beginResetModel()
        self.records = records
        valid = {record.task_id for record in records if record.status in _TERMINAL_STATUSES}
        self._checked_task_ids.intersection_update(valid)
        self.endResetModel()
        self.checked_changed.emit(len(self._checked_task_ids))

    def set_management_mode(self, enabled: bool) -> None:
        self.management_mode = bool(enabled)
        if not enabled:
            self._checked_task_ids.clear()
        if self.records:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.records) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        self.checked_changed.emit(len(self._checked_task_ids))

    def checked_task_ids(self) -> tuple[str, ...]:
        return tuple(record.task_id for record in self.records if record.task_id in self._checked_task_ids)

    def select_all_deletable(self) -> None:
        self._checked_task_ids = {
            record.task_id for record in self.records if record.status in _TERMINAL_STATUSES
        }
        if self.records:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.records) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        self.checked_changed.emit(len(self._checked_task_ids))

    def clear_checked(self) -> None:
        self._checked_task_ids.clear()
        if self.records:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.records) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        self.checked_changed.emit(0)

    def toggle(self, index: QModelIndex) -> bool:
        if not index.isValid():
            return False
        current = self.data(index, Qt.ItemDataRole.CheckStateRole)
        if current is None:
            return False
        next_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
        return self.setData(index, next_state, Qt.ItemDataRole.CheckStateRole)


class HistoryPage(QWidget):
    open_file_requested = Signal(str)
    open_folder_requested = Signal(str)
    copy_link_requested = Signal(str)
    thumbnail_requested = Signal(object)
    retry_requested = Signal(object)
    delete_requested = Signal(object)
    delete_many_requested = Signal(object)
    clear_terminal_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)
        heading_row = QHBoxLayout()
        heading = QLabel("历史记录")
        apply_typography(heading, FontRole.PAGE_TITLE)
        heading_row.addWidget(heading)
        heading_row.addStretch()
        self.manage_button = QPushButton("管理")
        self.manage_button.setAccessibleName("批量管理历史记录")
        heading_row.addWidget(self.manage_button)
        root.addLayout(heading_row)
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
        self.list_view.toggle_current_requested.connect(
            lambda: self.model.toggle(self.list_view.currentIndex())
        )
        self.list_view.select_all_checked_requested.connect(self.model.select_all_deletable)
        self.list_view.delete_checked_requested.connect(self._delete_checked)
        root.addWidget(self.list_view, 1)
        self.management_bar = QWidget()
        management = QHBoxLayout(self.management_bar)
        management.setContentsMargins(0, 0, 0, 0)
        self.selection_count_label = QLabel("已选择 0 项")
        apply_typography(self.selection_count_label, FontRole.SECONDARY)
        self.select_all_button = QPushButton("全选")
        self.clear_selection_button = QPushButton("取消全选")
        self.delete_selected_button = QPushButton("删除所选")
        self.delete_selected_button.setProperty("fluentAppearance", "danger")
        self.clear_history_button = QPushButton("清空历史")
        self.clear_history_button.setProperty("fluentAppearance", "danger")
        self.finish_manage_button = QPushButton("完成")
        for widget in (
            self.selection_count_label, self.select_all_button, self.clear_selection_button,
            self.delete_selected_button, self.clear_history_button, self.finish_manage_button,
        ):
            management.addWidget(widget)
        management.addStretch()
        self.management_bar.hide()
        root.addWidget(self.management_bar)
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
        self.manage_button.clicked.connect(lambda: self._set_management_mode(True))
        self.finish_manage_button.clicked.connect(lambda: self._set_management_mode(False))
        self.select_all_button.clicked.connect(self.model.select_all_deletable)
        self.clear_selection_button.clicked.connect(self.model.clear_checked)
        self.delete_selected_button.clicked.connect(self._delete_checked)
        self.clear_history_button.clicked.connect(self._clear_terminal)
        self.model.checked_changed.connect(self._checked_count_changed)
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

    def _set_management_mode(self, enabled: bool) -> None:
        self.model.set_management_mode(enabled)
        self.list_view.management_mode = enabled
        self.manage_button.setVisible(not enabled)
        self.management_bar.setVisible(enabled)
        self._checked_count_changed(len(self.model.checked_task_ids()))

    def _checked_count_changed(self, count: int) -> None:
        self.selection_count_label.setText(f"已选择 {count} 项")
        self.delete_selected_button.setEnabled(count > 0)
        self.clear_selection_button.setEnabled(count > 0)

    def _delete_checked(self) -> None:
        task_ids = self.model.checked_task_ids()
        if task_ids and self._confirm_delete_many(len(task_ids)):
            self.delete_many_requested.emit(task_ids)

    def _clear_terminal(self) -> None:
        if self._confirm_clear_terminal():
            self.clear_terminal_requested.emit()

    def _confirm_delete_many(self, count: int) -> bool:
        return DeleteHistoryBatchDialog(count, self).exec() == QDialog.DialogCode.Accepted

    def _confirm_clear_terminal(self) -> bool:
        return DeleteHistoryBatchDialog(None, self).exec() == QDialog.DialogCode.Accepted

    def show_management_result(self, deleted_count: int, retained_count: int) -> None:
        self.selection_count_label.setText(
            f"已删除 {deleted_count} 项；保留 {retained_count} 项不可删除记录"
            if retained_count
            else f"已删除 {deleted_count} 项"
        )

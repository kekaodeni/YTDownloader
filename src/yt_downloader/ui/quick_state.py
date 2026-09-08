"""Presentation-only state and incremental models shared by the QML views."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Property, Qt, Signal, Slot


class ViewState(QObject):
    changed = Signal()

    def __init__(self, parent=None, **values):
        super().__init__(parent)
        self._state = values

    @Property('QVariantMap', notify=changed)
    def state(self):
        return dict(self._state)

    def update(self, **values):
        if any(self._state.get(key) != value for key, value in values.items()):
            self._state.update(values)
            self.changed.emit()


class RowModel(QAbstractListModel):
    ItemRole = Qt.ItemDataRole.UserRole + 1
    countChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    @Property(int, notify=countChanged)
    def count(self):
        return len(self.rows)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def roleNames(self):
        return {self.ItemRole: b'item'}

    @Slot(int, result='QVariantMap')
    def get(self, index):
        return dict(self.rows[index]) if 0 <= index < len(self.rows) else {}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and 0 <= index.row() < len(self.rows) and role == self.ItemRole:
            return dict(self.rows[index.row()])
        return None

    def put(self, row):
        key = row['id']
        for index, old in enumerate(self.rows):
            if old['id'] == key:
                if old != row:
                    self.rows[index] = row
                    self.dataChanged.emit(self.index(index), self.index(index), [self.ItemRole])
                return
        index = len(self.rows)
        self.beginInsertRows(QModelIndex(), index, index)
        self.rows.append(row)
        self.endInsertRows()
        self.countChanged.emit()

    def remove(self, key):
        for index, row in enumerate(self.rows):
            if row['id'] == key:
                self.beginRemoveRows(QModelIndex(), index, index)
                self.rows.pop(index)
                self.endRemoveRows()
                self.countChanged.emit()
                return

    def replace(self, rows):
        # Keep delegate identity and selection on refresh; no reset for progress.
        valid = {row['id'] for row in rows}
        for old in tuple(self.rows):
            if old['id'] not in valid:
                self.remove(old['id'])
        for position, row in enumerate(rows):
            self.put(row)
            current = next(i for i, value in enumerate(self.rows) if value['id'] == row['id'])
            if current != position:
                self.beginMoveRows(QModelIndex(), current, current, QModelIndex(), position if current > position else position + 1)
                self.rows.insert(position, self.rows.pop(current))
                self.endMoveRows()

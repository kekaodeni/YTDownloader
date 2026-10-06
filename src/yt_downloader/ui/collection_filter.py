"""A stable, unsorted view of Collection rows; selection lives in the source."""
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Slot
from yt_downloader.ui.quick_state import RowModel


class CollectionFilter(QSortFilterProxyModel):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.choice = 'all'
        self.setSourceModel(source)
        self.setDynamicSortFilter(True)

    def filterAcceptsRow(self, row, parent):
        downloaded = bool(self.sourceModel().get(row).get('downloaded'))
        return self.choice == 'all' or downloaded == (self.choice == 'downloaded')

    def set_choice(self, choice):
        if choice != self.choice:
            self.beginFilterChange()
            self.choice = choice
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    @Slot(int, result='QVariantMap')
    def get(self, row):
        return self.data(self.index(row, 0), RowModel.ItemRole) or {}

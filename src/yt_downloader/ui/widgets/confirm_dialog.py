"""Small Fluent-styled confirmation dialog for destructive record-only actions."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout, QWidget


class DeleteHistoryDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("删除历史记录")
        self.setModal(True)
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        heading = QLabel("确定删除这条历史记录吗？")
        heading.setProperty("headingLevel", "2")
        root.addWidget(heading)
        record_title = QLabel(title)
        record_title.setWordWrap(True)
        root.addWidget(record_title)
        explanation = QLabel("只会删除本软件中的历史记录，不会删除已经下载的视频文件。")
        explanation.setProperty("secondary", True)
        explanation.setWordWrap(True)
        root.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        delete_button = QPushButton("删除记录")
        delete_button.setProperty("fluentAppearance", "danger")
        delete_button.setAccessibleName("确认删除历史记录")
        delete_button.clicked.connect(self.accept)
        buttons.addButton(delete_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

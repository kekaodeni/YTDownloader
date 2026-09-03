"""Small Fluent-styled confirmation dialog for destructive record-only actions."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout, QWidget

from yt_downloader.ui.localization import action_text, localize_dialog_button_box
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree


class DeleteHistoryDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("删除历史记录")
        self.setModal(True)
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        heading = QLabel("确定删除这条历史记录吗？")
        apply_typography(heading, FontRole.SECTION_TITLE)
        root.addWidget(heading)
        record_title = QLabel(title)
        record_title.setWordWrap(True)
        root.addWidget(record_title)
        explanation = QLabel("只会删除本软件中的历史记录，不会删除已经下载的视频文件。")
        apply_typography(explanation, FontRole.SECONDARY)
        explanation.setWordWrap(True)
        root.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        localize_dialog_button_box(buttons)
        delete_button = QPushButton(action_text("delete"))
        delete_button.setProperty("fluentAppearance", "danger")
        delete_button.setAccessibleName("确认删除历史记录")
        delete_button.clicked.connect(self.accept)
        buttons.addButton(delete_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_typography_tree(self)

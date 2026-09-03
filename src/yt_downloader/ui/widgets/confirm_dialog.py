"""Small Fluent-styled confirmation dialog for destructive record-only actions."""

from __future__ import annotations

from PySide6.QtCore import Signal
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


class DeleteHistoryBatchDialog(QDialog):
    def __init__(self, count: int | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        clearing_all = count is None
        self.setWindowTitle("清空历史记录" if clearing_all else "删除所选历史记录")
        self.setModal(True)
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        heading = QLabel(
            "确定清空所有可删除的历史记录吗？"
            if clearing_all
            else f"确定删除所选的 {count} 条历史记录吗？"
        )
        apply_typography(heading, FontRole.SECTION_TITLE)
        root.addWidget(heading)
        explanation = QLabel(
            "只会删除本软件中的终态历史记录；活动与排队记录会保留，也不会删除已经下载的视频文件。"
        )
        explanation.setWordWrap(True)
        apply_typography(explanation, FontRole.SECONDARY)
        root.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        localize_dialog_button_box(buttons)
        delete_button = QPushButton(action_text("delete"))
        delete_button.setProperty("fluentAppearance", "danger")
        delete_button.setAccessibleName("确认批量删除历史记录")
        delete_button.clicked.connect(self.accept)
        buttons.addButton(delete_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_typography_tree(self)


class RemoveActiveTaskDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("取消并删除任务")
        self.setModal(True)
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        heading = QLabel("取消下载并删除这张任务卡吗？")
        apply_typography(heading, FontRole.SECTION_TITLE)
        root.addWidget(heading)
        task_title = QLabel(title)
        task_title.setWordWrap(True)
        root.addWidget(task_title)
        explanation = QLabel("应用会先停止该任务、清理任务临时文件并保存取消状态；不会删除历史记录。")
        explanation.setWordWrap(True)
        apply_typography(explanation, FontRole.SECONDARY)
        root.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        localize_dialog_button_box(buttons)
        remove_button = QPushButton("取消并删除任务卡")
        remove_button.setProperty("fluentAppearance", "danger")
        remove_button.clicked.connect(self.accept)
        buttons.addButton(remove_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_typography_tree(self)


class IncompleteCleanupDialog(QDialog):
    open_folder_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("临时文件未完全清理")
        self.setModal(True)
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        heading = QLabel("部分任务临时文件未能清理")
        apply_typography(heading, FontRole.SECTION_TITLE)
        root.addWidget(heading)
        explanation = QLabel("文件可能仍被系统占用。你可以先打开文件夹处理，或确认后仍然移除任务卡。")
        explanation.setWordWrap(True)
        apply_typography(explanation, FontRole.SECONDARY)
        root.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        localize_dialog_button_box(buttons)
        open_button = QPushButton("打开文件夹")
        open_button.clicked.connect(self.open_folder_requested)
        buttons.addButton(open_button, QDialogButtonBox.ButtonRole.ActionRole)
        remove_button = QPushButton("仍然移除")
        remove_button.setProperty("fluentAppearance", "danger")
        remove_button.clicked.connect(self.accept)
        buttons.addButton(remove_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_typography_tree(self)

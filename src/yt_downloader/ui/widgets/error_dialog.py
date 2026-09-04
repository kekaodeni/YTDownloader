from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from yt_downloader.core.errors import AppError
from yt_downloader.ui.localization import localize_dialog_button_box
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree


class ErrorDialog(QDialog):
    def __init__(
        self,
        error: AppError,
        report: str,
        parent: QWidget | None = None,
        *,
        title_text: str = "下载失败",
        retry_callback=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.setModal(True)
        self.resize(620, 300)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)
        title = QLabel(title_text)
        apply_typography(title, FontRole.SECTION_TITLE)
        root.addWidget(title)
        summary = QLabel(error.user_message)
        summary.setWordWrap(True)
        root.addWidget(summary)
        self.details_button = QPushButton("错误详情 ︾")
        self.details_button.setCheckable(True)
        self.details_button.setAccessibleName("展开或折叠错误详情")
        self.details_button.clicked.connect(self._toggle_details)
        root.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.details = QPlainTextEdit(error.technical_message)
        self.details.setReadOnly(True)
        self.details.setVisible(False)
        self.details.setAccessibleName("技术错误详情")
        root.addWidget(self.details, 1)
        actions = QHBoxLayout()
        copy_button = QPushButton("复制错误报告")
        copy_button.setToolTip("复制已经脱敏的诊断信息")
        copy_button.setAccessibleName("复制错误报告")
        copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(report))
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        localize_dialog_button_box(close_box)
        close_box.rejected.connect(self.reject)
        actions.addWidget(copy_button)
        if retry_callback is not None:
            retry_button = QPushButton("重试")
            retry_button.clicked.connect(lambda: (self.accept(), retry_callback()))
            actions.addWidget(retry_button)
        actions.addStretch()
        actions.addWidget(close_box)
        root.addLayout(actions)
        apply_typography_tree(self)

    def _toggle_details(self, checked: bool) -> None:
        self.details.setVisible(checked)
        self.details_button.setText("错误详情 ︽" if checked else "错误详情 ︾")
        self.resize(self.width(), 520 if checked else 300)

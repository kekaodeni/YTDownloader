"""Fluent update dialog driven only by the centralized update state machine."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from yt_downloader.updates.models import UpdateCapability, UpdateManifest, UpdateProgress, UpdateState
from yt_downloader.ui.typography import FontRole, apply_typography, apply_typography_tree


class UpdateDialog(QDialog):
    download_requested = Signal()
    cancel_requested = Signal()
    install_requested = Signal()
    release_page_requested = Signal(str)

    def __init__(self, manifest: UpdateManifest, capability: UpdateCapability, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self.capability = capability
        self.setWindowTitle(f"YT Downloader {manifest.version} 更新")
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        heading = QLabel(f"YT Downloader {manifest.version} 已可用")
        apply_typography(heading, FontRole.SECTION_TITLE)
        root.addWidget(heading)
        notes = QLabel(manifest.notes_zh_cn)
        notes.setTextFormat(Qt.TextFormat.PlainText)
        notes.setWordWrap(True)
        root.addWidget(notes)
        self.status_label = QLabel("请选择更新方式。")
        apply_typography(self.status_label, FontRole.SECONDARY)
        root.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)
        actions = QHBoxLayout()
        self.release_button = QPushButton("打开发布页面")
        self.release_button.clicked.connect(lambda: self.release_page_requested.emit(manifest.release_url))
        self.download_button = QPushButton("下载并验证")
        self.download_button.setProperty("fluentAppearance", "primary")
        self.download_button.clicked.connect(self.download_requested)
        self.cancel_button = QPushButton("取消下载")
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.install_button = QPushButton("退出并更新")
        self.install_button.setProperty("fluentAppearance", "primary")
        self.install_button.clicked.connect(self.install_requested)
        self.later_button = QPushButton("稍后")
        self.later_button.clicked.connect(self.close)
        for button in (self.release_button, self.download_button, self.cancel_button, self.install_button, self.later_button):
            actions.addWidget(button)
        root.addLayout(actions)
        self.cancel_button.hide()
        self.install_button.hide()
        if capability is UpdateCapability.CHECK_ONLY:
            self.download_button.hide()
            self.status_label.setText("当前运行环境仅支持检查更新，请从发布页面手动升级。")
        else:
            self.release_button.hide()
        apply_typography_tree(self)

    def set_progress(self, progress: UpdateProgress) -> None:
        self.progress_bar.setRange(0, max(1, progress.total_bytes))
        self.progress_bar.setValue(progress.downloaded_bytes)

    def set_state(self, state: UpdateState) -> None:
        if state is UpdateState.DOWNLOADING:
            self.status_label.setText("正在下载更新…")
            self.progress_bar.show()
            self.download_button.hide()
            self.cancel_button.show()
            self.cancel_button.setEnabled(True)
        elif state is UpdateState.CANCELLING:
            self.status_label.setText("正在取消…")
            self.cancel_button.setEnabled(False)
        elif state is UpdateState.VERIFYING:
            self.status_label.setText("正在验证签名与文件完整性…")
            self.cancel_button.hide()
        elif state is UpdateState.READY_TO_INSTALL:
            self.progress_bar.setValue(self.progress_bar.maximum())
            self.cancel_button.hide()
            self.download_button.hide()
            if self.capability is UpdateCapability.AUTO_INSTALL:
                self.status_label.setText("更新已验证，可在退出应用后安全安装。")
                self.install_button.show()
            else:
                self.status_label.setText("更新已下载并验证；当前构建不支持自动安装。")
                self.release_button.show()
        elif state is UpdateState.FAILED:
            self.status_label.setText("更新操作失败，可以重试。")
            self.cancel_button.hide()
            if self.capability is not UpdateCapability.CHECK_ONLY:
                self.download_button.show()
        elif state is UpdateState.AVAILABLE:
            self.status_label.setText("请选择更新方式。")
            self.cancel_button.hide()
            if self.capability is not UpdateCapability.CHECK_ONLY:
                self.download_button.show()

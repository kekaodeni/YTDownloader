from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from yt_downloader import __version__


class AboutPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)
        heading = QLabel("关于")
        heading.setProperty("headingLevel", "1")
        root.addWidget(heading)
        card = QWidget()
        card.setProperty("fluentRole", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        name = QLabel("YT Downloader")
        name.setProperty("headingLevel", "2")
        layout.addWidget(name)
        layout.addWidget(QLabel(f"版本 {__version__}"))
        description = QLabel("简洁的 Windows 11 YouTube 单视频下载器，由 yt-dlp、FFmpeg 与 PySide6 驱动。")
        description.setWordWrap(True)
        description.setProperty("secondary", True)
        layout.addWidget(description)
        legal = QLabel("本软件与 YouTube 无关联。请仅下载您有权保存的内容。第三方组件许可见发布目录。")
        legal.setWordWrap(True)
        legal.setProperty("secondary", True)
        layout.addWidget(legal)
        root.addWidget(card)
        root.addStretch()


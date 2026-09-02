from collections.abc import Callable

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from yt_downloader import __version__
from yt_downloader.ui.typography import FontRole


PROJECT_URL = "https://github.com/kekaodeni/YTDownloader"


class AboutPage(QWidget):
    def __init__(
        self,
        parent=None,
        *,
        url_opener: Callable[[QUrl], bool] = QDesktopServices.openUrl,
    ) -> None:
        super().__init__(parent)
        self._url_opener = url_opener
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
        legal.setProperty("typographyRole", FontRole.CAPTION.value)
        layout.addWidget(legal)
        project_row = QHBoxLayout()
        self.project_button = QPushButton("在 GitHub 查看项目")
        self.project_button.setAccessibleName("在 GitHub 查看 YTDownloader 项目")
        self.project_button.setToolTip(PROJECT_URL)
        self.project_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.project_button.clicked.connect(self._open_project)
        self.copy_link_button = QPushButton("复制项目地址")
        self.copy_link_button.setAccessibleName("复制 YTDownloader GitHub 项目地址")
        self.copy_link_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(PROJECT_URL))
        self.copy_link_button.hide()
        project_row.addWidget(self.project_button)
        project_row.addWidget(self.copy_link_button)
        project_row.addStretch()
        layout.addLayout(project_row)
        self.link_status = QLabel("")
        self.link_status.setProperty("secondary", True)
        self.link_status.setWordWrap(True)
        self.link_status.hide()
        layout.addWidget(self.link_status)
        root.addWidget(card)
        root.addStretch()

    def _open_project(self) -> None:
        if self._url_opener(QUrl(PROJECT_URL)):
            self.link_status.hide()
            self.copy_link_button.hide()
            return
        self.link_status.setText(f"无法打开默认浏览器。你可以复制此地址：{PROJECT_URL}")
        self.link_status.show()
        self.copy_link_button.show()

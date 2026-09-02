from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from yt_downloader.ui.pages.about_page import PROJECT_URL, AboutPage


def test_project_link_opens_in_default_browser_and_is_accessible(qtbot) -> None:
    opened = []
    page = AboutPage(url_opener=lambda url: opened.append(url.toString()) or True)
    qtbot.addWidget(page)

    qtbot.mouseClick(page.project_button, Qt.MouseButton.LeftButton)

    assert opened == [PROJECT_URL]
    assert page.project_button.accessibleName() == "在 GitHub 查看 YTDownloader 项目"
    assert page.project_button.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_failed_project_link_shows_and_copies_exact_address(qtbot) -> None:
    page = AboutPage(url_opener=lambda _url: False)
    qtbot.addWidget(page)

    qtbot.mouseClick(page.project_button, Qt.MouseButton.LeftButton)

    assert page.link_status.isVisibleTo(page)
    assert PROJECT_URL in page.link_status.text()
    assert page.copy_link_button.isVisibleTo(page)
    qtbot.mouseClick(page.copy_link_button, Qt.MouseButton.LeftButton)
    assert QGuiApplication.clipboard().text() == PROJECT_URL

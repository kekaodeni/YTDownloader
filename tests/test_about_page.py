from PySide6.QtGui import QDesktopServices, QGuiApplication
from yt_downloader.ui.quick_window import PROJECT_URL

def test_project_link_opens_in_default_browser_and_is_accessible(quick_window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()) or True)
    quick_window.openProject()
    assert opened == [PROJECT_URL]
    assert quick_window.state['projectError'] == ''

def test_failed_project_link_shows_and_copies_exact_address(quick_window, monkeypatch):
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: False)
    quick_window.openProject()
    assert PROJECT_URL in quick_window.state['projectError']
    quick_window.copyProject()
    assert QGuiApplication.clipboard().text() == PROJECT_URL

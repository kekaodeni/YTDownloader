"""Bounded FIFO using the existing presenter, parse state and generation gate."""
from collections import deque
import time
from PySide6.QtCore import QObject, QTimer, Qt
from yt_downloader.core.models import ParseState
from .protocol import response, validate_message

class IncomingBrowserRequests(QObject):
    def __init__(self, window, parent=None, *, browser_seen=None):
        super().__init__(parent)
        self.window = window
        self.pending = deque()
        self.recent = {}
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.drain)
        self.browser_seen = browser_seen

    def receive(self, message):
        validate_message(message, ipc=True)
        if message.get('browser') and self.browser_seen: self.browser_seen(message['browser'])
        request_id = message['request_id']
        if message['action'] in {'ping', 'get_capabilities'}:
            return response(request_id, 'delivered', bridge_ready=True, app_running=True,
                            actions=['ping','send_url','get_capabilities'])
        if message['action'] == 'activate':
            self.show_window()
            return response(request_id, 'delivered')
        now = time.monotonic()
        self.recent = {key:value for key,value in self.recent.items() if now - value < 3}
        url = message['url']
        if url in self.recent: return response(request_id, 'delivered', duplicate=True)
        if len(self.pending) >= 16: return response(request_id, 'busy')
        self.recent[url] = now
        self.pending.append(url)
        self.show_window()
        self.timer.start()
        return response(request_id, 'delivered', queued=True)

    def show_window(self):
        self.window._select_page(0)
        root = self.window.root
        if root.visibility() == root.Visibility.Minimized: root.showNormal()
        else: root.show()
        root.requestActivate()  # Let Windows enforce foreground activation rules.

    def drain(self):
        page = self.window.download_page
        if page.parse_state in {ParseState.RUNNING, ParseState.SLOW, ParseState.CANCELLING}: return
        if not self.pending:
            self.timer.stop(); return
        page.set_url(self.pending.popleft())
        self.window.scroll_download_to_top()
        page.requestParse()  # Reuses Cookie/Profile/native yt-dlp; never requestDownload.

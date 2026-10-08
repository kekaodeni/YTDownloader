"""Honest, user-controlled per-browser Native Messaging associations."""
import time
from PySide6.QtCore import QTimer, QUrl, Slot, QProcess
from PySide6.QtGui import QDesktopServices
from yt_downloader.infrastructure.paths import AppPaths
from yt_downloader.browser_companion.registration import ConnectionManager
from yt_downloader.browser_companion.protocol import ProtocolError
from yt_downloader.ui.quick_state import ViewState


class BrowserCompanionPresenter(ViewState):
    def __init__(self, translator, parent=None, manager=None):
        super().__init__(parent, rows=[], noticeKey='', helpVisible=False)
        self.manager = manager or ConnectionManager(AppPaths.discover().data)
        self.seen = {}
        self.ids = {}
        self.probes = set()
        translator.languageChanged.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    @Slot()
    @Slot(str)
    def refresh(self, _locale=None):
        rows = []
        for browser in ('chrome', 'edge', 'firefox'):
            status = self.manager.status(browser)
            try:
                saved = self.manager.load().get('browsers', {}).get(browser, {})
                identity = saved.get('extension_id') or self.manager.identity(browser)
            except (OSError, ValueError, KeyError, ProtocolError):
                identity = ''
            if status == 'configured' and time.monotonic() - self.seen.get(browser, -1000) < 300:
                status = 'connected'
            rows.append(dict(browser=browser, name={'chrome':'Chrome', 'edge':'Microsoft Edge', 'firefox':'Firefox'}[browser],
                             statusKey='browser.' + status, extensionId=self.ids.get(browser, identity)))
        self.update(rows=rows)

    def mark_seen(self, browser):
        if browser in {'chrome', 'edge', 'firefox'}:
            self.seen[browser] = time.monotonic()
            self.refresh()

    @Slot(str, str)
    def setIdentity(self, browser, value):
        if browser in {'chrome', 'edge', 'firefox'}: self.ids[browser] = value.strip()

    @Slot(str, str)
    def perform(self, browser, action):
        if browser not in {'chrome', 'edge', 'firefox'}: return
        try:
            if action in {'install', 'repair'}:
                self.manager.install(browser, self.ids.get(browser) or None)
                self.seen.pop(browser, None)
                key = 'configured'
            elif action == 'remove':
                self.manager.remove(browser)
                self.seen.pop(browser, None)
                key = 'not_configured'
            elif action == 'folder':
                folder = self.manager.root / 'extensions' / browser
                if not folder.is_dir(): raise ProtocolError('not_configured')
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))): raise OSError()
                key = 'folder_opened'
            elif action == 'test':
                key = self.manager.status(browser)
                if key == 'configured':
                    self._probe(browser)
                    return
            else: return
            self.update(noticeKey='browser.' + key)
        except ProtocolError as error:
            key = error.status if error.status in {'bridge_missing','registration_conflict','unauthorized_extension','not_configured'} else 'operation_failed'
            self.update(noticeKey='browser.' + key)
        except (OSError, ValueError, KeyError):
            self.update(noticeKey='browser.operation_failed')
        self.refresh()

    @Slot()
    def toggleHelp(self): self.update(helpVisible=not self._state['helpVisible'])

    def _probe(self, browser):
        import uuid
        from yt_downloader.browser_companion.protocol import frame, decode_message
        import struct
        if self.probes: return
        process = QProcess(self)
        self.probes.add(process)
        request_id = uuid.uuid4().hex
        extension_id = self.manager.load()['browsers'][browser]['extension_id']
        args = ([str(self.manager.manifest_path(browser)),extension_id] if browser == 'firefox'
                else ['chrome-extension://' + extension_id + '/']) + ['--desktop-probe']
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.timeout.connect(process.kill)
        def started():
            process.write(frame(dict(protocol=1,action='ping',request_id=request_id)))
            process.closeWriteChannel()
        def finish(*_args):
            if process not in self.probes: return
            timer.stop()
            raw = bytes(process.readAllStandardOutput())
            key = 'operation_failed'
            try:
                if len(raw) < 4 or struct.unpack('<I', raw[:4])[0] != len(raw) - 4: raise ValueError()
                result = decode_message(raw[4:])
                if result.get('protocol') == 1 and result.get('request_id') == request_id and result.get('bridge_ready'):
                    key = 'test_in_browser'
            except (ValueError, ProtocolError): pass
            self.update(noticeKey='browser.' + key)
            self.probes.remove(process)
            process.deleteLater()
        process.started.connect(started)
        process.finished.connect(finish)
        process.errorOccurred.connect(lambda error: finish() if error == QProcess.ProcessError.FailedToStart else None)
        process.start(str(self.manager.bridge_path), args)
        timer.start(8000)

    def close(self):
        self.timer.stop()
        for process in tuple(self.probes):
            process.kill()
            process.waitForFinished(1000)

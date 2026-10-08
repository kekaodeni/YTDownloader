"""Per-browser setup, visible operation results and verified local connections."""
from pathlib import Path
import struct
import sys
import time
import uuid
from PySide6.QtCore import QProcess, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from yt_downloader.browser_companion.protocol import ProtocolError, decode_message, frame
from yt_downloader.browser_companion.registration import ConnectionManager
from yt_downloader.infrastructure.paths import AppPaths
from yt_downloader.infrastructure.runtime import resource_path
from yt_downloader.ui.quick_state import ViewState

BROWSERS = ('chrome', 'edge', 'firefox')
ADDRESSES = dict(chrome='chrome://extensions', edge='edge://extensions', firefox='about:debugging')

class BrowserCompanionPresenter(ViewState):
    operationStarted = Signal(str, str)
    operationFinished = Signal(str, str)

    def __init__(self, translator, parent=None, manager=None, *, dialogs=None, probe_timeout_ms=8000):
        super().__init__(parent, rows=[], noticeKey='', helpVisible=False, activeBrowser='chrome',
                         sourceEnvironment=not getattr(sys, 'frozen', False))
        self.manager = manager or ConnectionManager(AppPaths.discover().data)
        self.translator, self.dialogs = translator, dialogs
        self.seen, self.ids, self.results, self.operations, self.tested = {}, {}, {}, {}, {}
        self.advanced, self.probes = set(), set()
        self.probe_timeout_ms = probe_timeout_ms
        self._closed = False
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
        for browser in BROWSERS:
            status = self.manager.status(browser)
            try:
                saved = self.manager.load().get('browsers', {}).get(browser, {})
                identity = saved.get('extension_id') or self.manager.identity(browser)
            except (OSError, ValueError, KeyError):
                identity = ''
            configured = status == 'configured'
            if not configured:
                self.tested.pop(browser, None)
            connected = configured and time.monotonic() - self.seen.get(browser, -1000) < 300
            host_ready = configured and (browser in self.tested or connected)
            status_key = 'connected' if connected else 'host_ready' if host_ready else status
            result = self.results.get(browser, {})
            root = getattr(self.manager, 'root', Path())
            bridge = getattr(self.manager, 'bridge_path', None)
            rows.append(dict(browser=browser,
                name=dict(chrome='Chrome', edge='Microsoft Edge', firefox='Firefox')[browser],
                statusKey='browser.' + status_key, extensionId=self.ids.get(browser, identity),
                configured=configured, hostReady=host_ready, connected=connected,
                connectionState='CONNECTED' if connected else 'HOST_READY' if host_ready else 'NOT_CONFIGURED' if status == 'not_configured' else 'NEEDS_ATTENTION',
                busy=browser in self.operations, action=self.operations.get(browser, ''),
                advanced=browser in self.advanced, noticeKey=result.get('key', ''),
                noticeArea=result.get('area', ''), noticeError=result.get('error', False),
                bridgeExists=bool(bridge and bridge.is_file()), bridgePath=str(bridge or ''),
                manifestPath=str(root / (browser + '.json')), folderPath=str(root / 'extensions' / browser),
                installAddress=ADDRESSES[browser]))
        self.update(rows=rows)

    def mark_seen(self, browser):
        if browser in BROWSERS:
            self.seen[browser] = time.monotonic()
            self.refresh()

    @Slot(str)
    def selectBrowser(self, browser):
        if browser in BROWSERS:
            self.update(activeBrowser=browser)

    @Slot(str)
    def toggleAdvanced(self, browser):
        if browser in self.advanced:
            self.advanced.remove(browser)
        elif browser in BROWSERS:
            self.advanced.add(browser)
        self.refresh()

    @Slot(str, str)
    def setIdentity(self, browser, value):
        if browser in BROWSERS and browser not in self.operations:
            self.ids[browser] = value.strip()

    @Slot()
    def toggleHelp(self):
        self.update(helpVisible=not self._state['helpVisible'])

    def _notice(self, browser, key, area, *, error=False):
        self.results[browser] = dict(key='browser.' + key, area=area, error=error)
        self.update(noticeKey='browser.' + key)
        self.refresh()

    def _complete(self, browser, action, key, *, error=False):
        self.operations.pop(browser, None)
        self._notice(browser, key, action, error=error)
        self.operationFinished.emit(browser, action)

    @Slot(str, str)
    def perform(self, browser, action):
        if (self._closed or browser not in BROWSERS or browser in self.operations or
                action not in {'install', 'repair', 'remove', 'folder', 'test', 'copy_address', 'copy_build'}):
            return
        self.operations[browser] = action
        self._notice(browser, 'working', action)
        self.operationStarted.emit(browser, action)
        if action == 'remove' and self.dialogs is not None:
            self._notice(browser, 'remove_confirm', action)
            def answer(accepted):
                if accepted:
                    QTimer.singleShot(0, lambda: self._execute(browser, action))
                else:
                    self._complete(browser, action, 'remove_cancelled')
            self.dialogs.confirm(self.translator.text('browser.remove'), self.translator.text('browser.remove_confirm'),
                                 self.translator.text('browser.remove'), answer,
                                 cancel=self.translator.text('common.cancel'))
        else:
            QTimer.singleShot(0, lambda: self._execute(browser, action))

    def _execute(self, browser, action):
        if self._closed:
            return
        try:
            if action in {'install', 'repair'}:
                self.manager.install(browser, self.ids.get(browser) or None)
                self.seen.pop(browser, None)
                self.tested.pop(browser, None)
                self._notice(browser, 'checking', action)
                self._probe(browser, action)
                return
            if action == 'remove':
                removed = self.manager.remove(browser)
                self.seen.pop(browser, None)
                self.tested.pop(browser, None)
                key = 'removed' if removed else 'not_configured'
            elif action == 'folder':
                folder = self.manager.root / 'extensions' / browser
                if not folder.is_dir():
                    raise ProtocolError('folder_missing')
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                    raise ProtocolError('open_failed')
                key = 'folder_opened'
            elif action == 'test':
                if not self.manager.bridge_path.is_file():
                    raise ProtocolError('bridge_missing')
                status = self.manager.status(browser)
                if status != 'configured':
                    raise ProtocolError(status)
                self._notice(browser, 'checking', action)
                self._probe(browser, action)
                return
            elif action == 'copy_address':
                QGuiApplication.clipboard().setText(ADDRESSES[browser])
                key = 'address_copied'
            else:
                command = 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + str(resource_path('scripts/build_browser_bridge.ps1')) + '"'
                QGuiApplication.clipboard().setText(command)
                key = 'build_copied'
            self._complete(browser, action, key)
        except ProtocolError as error:
            allowed = {'bridge_missing', 'registration_conflict', 'unauthorized_extension', 'not_configured',
                       'repair_needed', 'folder_missing', 'open_failed'}
            self._complete(browser, action, error.status if error.status in allowed else 'operation_failed', error=True)
        except (OSError, ValueError, KeyError):
            self._complete(browser, action, 'operation_failed', error=True)

    def _probe(self, browser, action='test'):
        extension_id = self.manager.load()['browsers'][browser]['extension_id']
        process = QProcess(self)
        self.probes.add(process)
        request_id = uuid.uuid4().hex
        args = ([str(self.manager.manifest_path(browser)), extension_id] if browser == 'firefox'
                else ['chrome-extension://' + extension_id + '/']) + ['--desktop-probe']
        timer = QTimer(process)
        timer.setSingleShot(True)
        timed_out = False
        def timeout():
            nonlocal timed_out
            timed_out = True
            process.kill()
        timer.timeout.connect(timeout)
        def started():
            process.write(frame(dict(protocol=1, action='ping', request_id=request_id)))
            process.closeWriteChannel()
        def finish(*_args):
            if process not in self.probes:
                return
            timer.stop()
            raw = bytes(process.readAllStandardOutput())
            key, error = ('test_timeout' if timed_out else 'operation_failed'), True
            try:
                if process.exitCode() != 0 or len(raw) < 4 or struct.unpack('<I', raw[:4])[0] != len(raw) - 4:
                    raise ValueError()
                result = decode_message(raw[4:])
                if (result.get('protocol') == 1 and result.get('request_id') == request_id and
                        result.get('bridge_ready') is True and result.get('status') in {'accepted', 'delivered'}):
                    if result.get('app_running') is True:
                        self.tested[browser] = True
                        key, error = ('connection_configured' if action in {'install', 'repair'} else 'test_in_browser'), False
                    else:
                        key = 'ipc_unavailable'
            except (ValueError, ProtocolError):
                pass
            self.probes.remove(process)
            self._complete(browser, action, key, error=error)
            process.deleteLater()
        process.started.connect(started)
        process.finished.connect(finish)
        process.errorOccurred.connect(lambda error: finish() if error == QProcess.ProcessError.FailedToStart else None)
        process.start(str(self.manager.bridge_path), args)
        timer.start(self.probe_timeout_ms)

    def close(self):
        self._closed = True
        self.timer.stop()
        for process in tuple(self.probes):
            process.kill()
            process.waitForFinished(1000)

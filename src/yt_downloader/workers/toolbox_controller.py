"""GUI-thread orchestration of shared metadata and standalone asset services."""
import threading
from PySide6.QtCore import QObject, QThreadPool, Signal
from yt_downloader.core.models import ParseState
from yt_downloader.workers.metadata_process import MetadataProcessController
from yt_downloader.workers.request_gate import LatestRequestGate
from yt_downloader.workers.function_worker import FunctionWorker


class ToolboxController(QObject):
    error = Signal(object, object)
    completed = Signal(object, object)
    failed = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, page, config_factory, service_factory, parent=None):
        super().__init__(parent)
        self.page = page
        self.config_factory = config_factory
        self.service_factory = service_factory
        self.metadata = MetadataProcessController(self)
        self.gate = LatestRequestGate()
        self.workers = []
        self.cancel_event = None
        self.preview_cancel = None
        self.preview_gate = LatestRequestGate()
        page.parse_requested.connect(self.parse)
        page.parse_cancel_requested.connect(self.metadata.cancel)
        page.tool_requested.connect(self.execute)
        page.tool_cancel_requested.connect(self.cancel_tool)
        page.preview_requested.connect(self.preview)
        self.metadata.state_changed.connect(self._parse_state)
        self.metadata.result.connect(self._metadata_result)
        self.metadata.failed.connect(self._metadata_error)
        self.metadata.timed_out.connect(self._metadata_error)
        self.metadata.cancelled.connect(lambda token: self.gate.finish(token))

    @property
    def is_busy(self):
        return self.metadata.is_running or bool(self.workers)

    def _parse_state(self, state):
        self.page.set_parse_state(state)
        self.busy_changed.emit(self.is_busy)

    def parse(self, url):
        if self.page.state['toolBusy']:
            return
        token = self.gate.begin(url)
        self.metadata.start(token, url, self.config_factory(self.page, require_formats=False))

    def _metadata_result(self, token, media):
        if self.gate.deliver(token, self.page.show_video, media):
            self.gate.finish(token)

    def _metadata_error(self, token, error):
        if self.gate.is_current(token):
            self.gate.finish(token)
            self.page.set_cookie_parse_error(error.code, error.user_message)
            self.error.emit(error, self.page.requestParse)

    def execute(self, request):
        if self.page.state['toolBusy']:
            return
        self.page.update(toolBusy=True, resultFiles=[], toolStatus='')
        cancel = threading.Event()
        self.cancel_event = cancel
        worker = FunctionWorker(self.service_factory().execute, request, cancel)
        self.workers.append(worker)
        worker.signals.result.connect(lambda result: self._completed(request, result))
        worker.signals.error.connect(lambda error: self._failed(request, error))
        worker.signals.finished.connect(lambda: self._finished(worker))
        self.busy_changed.emit(True)
        QThreadPool.globalInstance().start(worker)

    def preview(self, url):
        if self.preview_cancel:
            self.preview_cancel.set()
        token = self.preview_gate.begin(url)
        cancel = threading.Event()
        self.preview_cancel = cancel
        worker = FunctionWorker(self.service_factory().resolver.fetch_thumbnail, url, cancel)
        self.workers.append(worker)
        worker.signals.result.connect(lambda data: self._preview_result(token, url, data))
        worker.signals.finished.connect(lambda: self._preview_finished(worker, token))
        self.busy_changed.emit(True)
        QThreadPool.globalInstance().start(worker)

    def _preview_result(self, token, url, data):
        self.preview_gate.deliver(token, lambda payload: self.page.set_tool_preview(url, payload), data)

    def _preview_finished(self, worker, token):
        if worker in self.workers:
            self.workers.remove(worker)
        if self.preview_gate.finish(token):
            self.preview_cancel = None
        self.busy_changed.emit(self.is_busy)

    def _completed(self, request, result):
        self.page.tool_completed(result)
        self.completed.emit(request, result)

    def _failed(self, request, error):
        self.page.update(toolBusy=False)
        self.failed.emit(request)
        self.error.emit(error, lambda: self.execute(request))

    def _finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        self.cancel_event = None
        self.page.update(toolBusy=False)
        self.busy_changed.emit(self.is_busy)

    def cancel_tool(self):
        if self.cancel_event:
            self.cancel_event.set()

    def cancel(self):
        self.metadata.cancel()
        self.cancel_tool()
        if self.preview_cancel:
            self.preview_cancel.set()
        self.preview_gate.current = None

    def shutdown(self):
        self.cancel()
        self.metadata.shutdown()

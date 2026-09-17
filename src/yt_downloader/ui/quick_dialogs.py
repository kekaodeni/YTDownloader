"""Asynchronous presentation sessions. No nested event loops or QML business code."""
from __future__ import annotations

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication

from yt_downloader.ui.quick_state import ViewState, RowModel
from yt_downloader.updates.models import UpdateCapability, UpdateState


class DialogBridge(ViewState):
    sessionsChanged = Signal()
    directory_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions = []
        self._directory_callbacks = {}
        self._serial = 0
        self._model = RowModel(self)

    @Property(QObject, constant=True)
    def model(self):
        return self._model

    @Property('QVariantList', notify=sessionsChanged)
    def sessions(self):
        return list(self._sessions)

    def show(self, session):
        if session not in self._sessions:
            self._sessions.append(session)
            self._model.put(dict(id=str(id(session)), session=session))
            session.closed.connect(lambda: QTimer.singleShot(180, lambda: self._dispose(session)))
            self.sessionsChanged.emit()
        session.update(open=True)

    def _dispose(self, session):
        if session in self._sessions:
            self._sessions.remove(session)
            self._model.remove(str(id(session)))
            self.sessionsChanged.emit()
            session.deleteLater()

    def confirm(self, title, message, accept, callback, *, cancel='取消', folder_callback=None):
        session = ConfirmSession(self, title, message, accept, callback, cancel, folder_callback)
        session.show()
        return session

    def pick_directory(self, title, current, callback):
        self._serial += 1
        key = str(self._serial)
        self._directory_callbacks[key] = callback
        self.directory_requested.emit(key, QUrl.fromLocalFile(current).toString())

    @Slot(str, str)
    def directorySelected(self, key, url):
        callback = self._directory_callbacks.pop(key, None)
        if callback and url:
            callback(QUrl(url).toLocalFile())


class DialogSession(ViewState):
    closed = Signal()
    focusRequested = Signal()

    def __init__(self, bridge, *, kind, title, modal=False, **values):
        super().__init__(bridge, kind=kind, title=title, open=False, modal=modal,
                         message='', closeEnabled=True, **values)
        self.bridge = bridge

    def show(self):
        self.bridge.show(self)

    def raise_(self):
        self.focusRequested.emit()

    def activateWindow(self):
        self.focusRequested.emit()

    @Slot()
    def reject(self):
        self.close()

    @Slot()
    def close(self):
        if self._state['open']:
            self.update(open=False)
            self.closed.emit()


class ConfirmSession(DialogSession):
    def __init__(self, bridge, title, message, accept, callback, cancel, folder_callback):
        super().__init__(bridge, kind='confirm', title=title, modal=True,
                         acceptText=accept, cancelText=cancel, hasFolder=folder_callback is not None)
        self.update(message=message)
        self.callback = callback
        self.folder_callback = folder_callback
        self._resolved = False

    @Slot(bool)
    def answer(self, accepted):
        if self._resolved:
            return
        self._resolved = True
        self.close()
        self.callback(accepted)

    @Slot()
    def reject(self):
        self.answer(False)

    @Slot()
    def openFolder(self):
        if self.folder_callback:
            self.folder_callback()


class ErrorSession(DialogSession):
    def __init__(self, error, report, parent, *, title_text='下载失败', retry_callback=None):
        super().__init__(parent.dialogs, kind='error', title=title_text, modal=True,
                         details=error.technical_message, hasRetry=retry_callback is not None)
        self.update(message=error.user_message)
        self.report = report
        self.retry_callback = retry_callback

    @Slot()
    def copyReport(self):
        QGuiApplication.clipboard().setText(self.report)

    @Slot()
    def retry(self):
        if self._state['open'] and self.retry_callback:
            self.close()
            self.retry_callback()


class UpdateSession(DialogSession):
    download_requested = Signal()
    cancel_requested = Signal()
    install_requested = Signal()
    release_page_requested = Signal(str)

    def __init__(self, manifest, capability, parent):
        super().__init__(parent.dialogs, kind='update', title=f'YT Downloader {manifest.version} 更新',
                         notes=manifest.notes_zh_cn, canDownload=capability is not UpdateCapability.CHECK_ONLY,
                         canRelease=capability is UpdateCapability.CHECK_ONLY, canInstall=False,
                         canCancel=False, cancelEnabled=True, progressVisible=False, progress=0.0)
        self.manifest = manifest
        self.capability = capability
        self.update(message='当前运行环境仅支持检查更新，请从发布页面手动升级。' if capability is UpdateCapability.CHECK_ONLY else '请选择更新方式。')

    def set_progress(self, progress):
        self.update(progress=progress.downloaded_bytes / max(1, progress.total_bytes))

    def set_state(self, state):
        if state is UpdateState.DOWNLOADING:
            self.update(message='正在下载更新…', progressVisible=True, canDownload=False, canCancel=True, cancelEnabled=True)
        elif state is UpdateState.CANCELLING:
            self.update(message='正在取消…', cancelEnabled=False)
        elif state is UpdateState.VERIFYING:
            self.update(message='正在验证签名与文件完整性…', canCancel=False)
        elif state is UpdateState.READY_TO_INSTALL:
            install = self.capability is UpdateCapability.AUTO_INSTALL
            self.update(progress=1.0, canCancel=False, canDownload=False, canInstall=install,
                        canRelease=not install,
                        message='更新已验证，可在退出应用后安全安装。' if install else '更新已下载并验证；当前构建不支持自动安装。')
        elif state in {UpdateState.PREPARING_INSTALL, UpdateState.PREPARING_EXIT}:
            self.update(message='正在复核更新并准备退出…', canInstall=False, canDownload=False, canCancel=False)
        elif state in {UpdateState.FAILED, UpdateState.AVAILABLE}:
            self.update(message='更新操作失败，可以重试。' if state is UpdateState.FAILED else '请选择更新方式。',
                        canCancel=False, canDownload=self.capability is not UpdateCapability.CHECK_ONLY)

    @Slot(str)
    def action(self, name):
        if name == 'download' and self._state['canDownload']:
            self.download_requested.emit()
        elif name == 'cancel' and self._state['canCancel'] and self._state['cancelEnabled']:
            self.cancel_requested.emit()
        elif name == 'install' and self._state['canInstall']:
            self.install_requested.emit()
        elif name == 'release' and self._state['canRelease']:
            self.release_page_requested.emit(self.manifest.release_url)

"""Asynchronous presentation sessions. No nested event loops or QML business code."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication

from yt_downloader import __version__
from yt_downloader.core.formatting import format_bytes, format_speed, format_eta
from yt_downloader.ui.quick_state import ViewState, RowModel
from yt_downloader.updates.models import UpdateCapability, UpdateState


class DialogBridge(ViewState):
    sessionsChanged = Signal()
    directory_requested = Signal(str, str)

    def __init__(self, parent=None, translator=None):
        super().__init__(parent)
        self._translator = translator
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

    @Slot(str, str, result=QObject)
    def info(self, title, message):
        session = DialogSession(self, kind='info', title=title, modal=True)
        session.update(message=message)
        session.show()
        return session

    def cookie_editor(self, profile, callback, test_callback, pick_callback):
        session = CookieEditorSession(self, profile, callback, test_callback, pick_callback)
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
        self._translator = bridge._translator
        self._source_texts = {key: str(value) for key, value in self._state.items()
                              if key in {'title', 'message', 'acceptText', 'cancelText', 'dismissText', 'downloadText', 'progressText', 'fileLabel', 'durationText', 'previewText', 'applyText'}
                              and isinstance(value, str)}
        if self._translator is not None:
            self._translator.languageChanged.connect(self._refresh_localized)
            self._refresh_localized()

    def update(self, **values):
        localizable = {'title', 'message', 'acceptText', 'cancelText', 'dismissText', 'downloadText', 'progressText', 'fileLabel', 'durationText', 'previewText', 'applyText'}
        for key in localizable.intersection(values):
            if isinstance(values[key], str):
                self._source_texts[key] = values[key]
                if self._translator is not None:
                    values[key] = self._translator.sourceText(values[key])
        super().update(**values)

    def _refresh_localized(self, _locale=None):
        if self._translator is not None:
            super().update(**{key: self._translator.sourceText(value)
                              for key, value in self._source_texts.items()})

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


class CookieEditorSession(DialogSession):
    """Reference-only Cookie profile editor used by both settings actions."""
    def __init__(self, bridge, profile, callback, test_callback, pick_callback):
        super().__init__(bridge, kind='cookie', title='Cookie 配置', modal=True,
                         profileId=profile.id if profile else '',
                         name=profile.name if profile else '',
                         domain=profile.domain_hint if profile else '',
                         source=profile.source_type if profile else 'browser',
                         browser=profile.browser if profile else 'chrome',
                         browserProfile=profile.browser_profile if profile else '', filePath=profile.cookie_file if profile else '',
                         fileLabel=(Path(profile.cookie_file).name if profile and profile.cookie_file else '未选择文件'))
        self.callback = callback
        self.test_callback = test_callback
        self.pick_callback = pick_callback

    @Slot(str, str)
    def setField(self, name, value):
        if name in {'name', 'domain', 'source', 'browser', 'browserProfile'}:
            self.update(**{name: value})

    @Slot(str)
    def setSource(self, source):
        if source in {'browser', 'file'}:
            self.update(source=source)

    def set_file_path(self, path):
        self.update(filePath=str(path), fileLabel=Path(path).name if path else '未选择文件')

    @Slot()
    def browse(self):
        self.pick_callback()

    @Slot()
    def test(self):
        self.test_callback(self)

    @Slot()
    def save(self):
        values = {'id': self._state['profileId'], 'name': self._state['name'],
                  'domain': self._state['domain'], 'source': self._state['source'],
                  'browser': self._state['browser'], 'browser_profile': self._state['browserProfile'],
                  'file_path': self._state['filePath']}
        if self.callback(values, self):
            self.close()


class ErrorSession(DialogSession):
    ACTION_LABELS = {
        'OPEN_COOKIE_MANAGER': 'download.manage_cookie',
        'REPARSE': 'download.reparse',
        'RETRY': 'action.retry',
        'CHECK_APP_UPDATE': 'update.action_check',
        'CLOSE': 'common.close',
    }

    def __init__(self, error, report, parent, *, title_text='下载失败', retry_callback=None,
                 actions=(), action_callbacks=None):
        no_media = error.code == 'NO_DOWNLOADABLE_MEDIA'
        super().__init__(parent.dialogs, kind='empty_media' if no_media else 'error', title=title_text, modal=True,
                         details=error.technical_message, hasRetry=retry_callback is not None and not no_media)
        self.error = error
        self._title_source = title_text
        self._message_source = error.user_message
        self.report = report
        self.retry_callback = None if no_media else retry_callback
        self.action_callbacks = dict(action_callbacks or {})
        self._error_actions = () if no_media else tuple(actions)
        if self._translator is not None:
            self._translator.languageChanged.connect(self._refresh_error_localized)
        self._refresh_error_localized()

    def _refresh_error_localized(self, _locale=None):
        if self._translator is None:
            title = self._title_source
            message = self._message_source
            labels = {action: action for action in self._error_actions}
        else:
            title = self._translator.text(self.error.title_message_id) if self.error.title_message_id else self._translator.sourceText(self._title_source)
            site = self.error.context.cookie_site
            if site in {'Bilibili', 'Douyin'}:
                site = self._translator.text('cookie.site_bilibili' if site == 'Bilibili' else 'cookie.site_douyin')
            message = self._translator.text(self.error.body_message_id, {'site': site}) if self.error.body_message_id else self._translator.sourceText(self._message_source)
            if self.error.code == 'NO_DOWNLOADABLE_MEDIA':
                from yt_downloader.services.cookie_service import cookie_site_domain
                title = self._translator.text(self.error.title_message_id or 'media.no_downloadable.title')
                body_key = ('media.no_downloadable.post_body' if site == 'X' or
                            cookie_site_domain(self.error.context.url) == 'x.com' else 'media.no_downloadable.body')
                message = self._translator.text(body_key)
            labels = {action: self._translator.text(self.ACTION_LABELS.get(action, 'common.close'))
                      for action in self._error_actions}
        super().update(title=title, message=message,
                       errorActions=[{'id': action, 'label': labels[action], 'primary': index == 0}
                                     for index, action in enumerate(self._error_actions)])

    @Slot()
    def copyReport(self):
        QGuiApplication.clipboard().setText(self.report)

    @Slot()
    def retry(self):
        if self._state['open'] and self.retry_callback:
            self.close()
            self.retry_callback()

    @Slot(str)
    def runAction(self, action_id):
        callback = self.action_callbacks.get(str(action_id))
        if not self._state['open'] or callback is None:
            return
        self.close()
        callback()


class UpdateSession(DialogSession):
    download_requested = Signal()
    cancel_requested = Signal()
    install_requested = Signal()
    release_page_requested = Signal(str)

    def __init__(self, manifest, capability, parent):
        super().__init__(parent.dialogs, kind='update', title=f'YT Downloader {manifest.version} 更新',
                         notes=manifest.notes_zh_cn, language='zh-CN',
                         currentVersion=__version__, targetVersion=str(manifest.version),
                         packageSize=format_bytes(manifest.package.compressed_size),
                         canDownload=False, canRelease=True, canInstall=False,
                         canCancel=False, cancelEnabled=True, progressVisible=False, progress=0.0,
                         progressText='', downloadText='下载并安装' if capability is UpdateCapability.AUTO_INSTALL else '下载并验证',
                         dismissText='取消')
        self.manifest = manifest
        self.capability = capability
        self._latest_progress = None
        self._update_state = UpdateState.AVAILABLE
        self.set_state(UpdateState.AVAILABLE)

    def _progress_values(self, progress=None):
        translator = self._translator
        if progress is None:
            values = {
                'percent': '0%', 'downloaded': '0 B',
                'total': self._state.get('packageSize', '—'),
                'speed': translator.text('common.calculating') if translator else '计算中',
                'eta': translator.text('common.calculating') if translator else '计算中',
            }
            return 0.0, translator.text('update.progress_text', values) if translator else (
                f"{values['percent']} · {values['downloaded']} / {values['total']} · {values['speed']} · 剩余 {values['eta']}")
        fraction = min(1.0, max(0.0, progress.downloaded_bytes / max(1, progress.total_bytes)))
        values = {
            'percent': f'{fraction:.0%}',
            'downloaded': format_bytes(progress.downloaded_bytes),
            'total': format_bytes(progress.total_bytes),
            'speed': format_speed(progress.speed) if progress.speed is not None else translator.text('common.calculating') if translator else '计算中',
            'eta': format_eta(progress.eta) if progress.eta is not None else translator.text('common.calculating') if translator else '计算中',
        }
        if translator:
            return fraction, translator.text('update.progress_text', values)
        return fraction, f"{values['percent']} · {values['downloaded']} / {values['total']} · {values['speed']} · 剩余 {values['eta']}"

    def _refresh_localized(self, _locale=None):
        super()._refresh_localized(_locale)
        if not hasattr(self, '_update_state') or self._translator is None:
            return
        if self._latest_progress is not None:
            fraction, text = self._progress_values(self._latest_progress)
            from yt_downloader.ui.quick_state import ViewState
            ViewState.update(self, progress=fraction, progressText=text)
        elif self._update_state is UpdateState.DOWNLOADING:
            fraction, text = self._progress_values()
            from yt_downloader.ui.quick_state import ViewState
            ViewState.update(self, progress=fraction, progressText=text)

    @Slot(str)
    def setLanguage(self, language):
        if language in {'zh-CN', 'en'}:
            self.update(language=language, notes=self.manifest.notes_en if language == 'en' else self.manifest.notes_zh_cn)

    @Slot()
    def reject(self):
        if self._state['closeEnabled']:
            super().reject()

    def set_progress(self, progress):
        self._latest_progress = progress
        fraction, progress_text = self._progress_values(progress)
        from yt_downloader.ui.quick_state import ViewState
        ViewState.update(self, progress=fraction, progressText=progress_text)

    def set_state(self, state, *, operation=''):
        if state is UpdateState.DOWNLOADING and self._update_state is not UpdateState.DOWNLOADING:
            self._latest_progress = None
        self._update_state = state
        install = self.capability is UpdateCapability.AUTO_INSTALL
        download = self.capability is not UpdateCapability.CHECK_ONLY
        values = dict(canDownload=False, canInstall=False, canCancel=False, cancelEnabled=True,
                      closeEnabled=True, canRelease=True, progressVisible=False, dismissText='关闭')
        if state is UpdateState.DOWNLOADING:
            values.update(message='正在下载更新，可关闭此窗口并稍后在关于页面查看进度。', progressVisible=True, canCancel=True)
            fraction, progress_text = self._progress_values(self._latest_progress)
            values.update(progress=fraction, progressText=progress_text)
        elif state is UpdateState.CANCELLING:
            values.update(message='正在取消…', progressVisible=True, canCancel=True, cancelEnabled=False)
        elif state is UpdateState.VERIFYING:
            values.update(message='正在验证签名与文件完整性…', progressVisible=True)
        elif state is UpdateState.READY_TO_INSTALL:
            values.update(progress=1.0, canInstall=install, dismissText='稍后',
                          message='更新已验证，确认后将安装并重启。' if install else '更新已下载并验证；当前构建不支持自动安装。')
        elif state in {UpdateState.PREPARING_INSTALL, UpdateState.PREPARING_EXIT}:
            values.update(message='正在复核更新并准备退出…', closeEnabled=False, canRelease=False)
        elif state is UpdateState.FAILED:
            values.update(message='更新操作失败，可以重试。', canInstall=install and operation == 'prepare',
                          canDownload=download and operation == 'download')
        else:
            message = ('下载完成后需确认安装并重启。' if install else '当前构建仅支持下载并验证更新。') if download else '当前运行环境仅支持检查更新，请从发布页面手动升级。'
            values.update(message=message, canDownload=download, dismissText='取消')
        self.update(**values)

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

"""Qt Quick shell and the application-facing presentation ports."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQuick import QQuickWindow

from yt_downloader import __version__
from yt_downloader.infrastructure.runtime import resource_path
from yt_downloader.ui.quick_dialogs import DialogBridge
from yt_downloader.ui.quick_download import DownloadPresenter
from yt_downloader.ui.quick_history import HistoryPresenter
from yt_downloader.ui.quick_images import ImageStore
from yt_downloader.ui.quick_settings import SettingsPresenter
from yt_downloader.ui.quick_state import ViewState
from yt_downloader.ui.quick_theme import QuickTheme

PROJECT_URL = 'https://github.com/kekaodeni/YTDownloader'


class MainWindow(ViewState):
    cancel_all_requested = Signal()
    cancel_update_requested = Signal()
    show_update_requested = Signal()
    scrollToTopRequested = Signal()

    def __init__(self, settings, *, ytdlp_version, ffmpeg_description, theme=None, icons=None):
        super().__init__(None, page=0, reduceMotion=settings.reduce_motion, allowClose=False,
                         updateVisible=False, updateText='', version=__version__, projectError='')
        self._busy = False
        self._update_busy = False
        self._closing_after_cancel = False
        self._confirming_close = False
        self.theme = theme or QuickTheme(QGuiApplication.instance())
        self.images = ImageStore()
        self.dialogs = DialogBridge(self)
        self.dialogs.sessionsChanged.connect(self._finish_close)
        self.download_page = DownloadPresenter(settings.download_directory, self.images, self)
        self.history_page = HistoryPresenter(self.dialogs, self)
        self.settings_page = SettingsPresenter(settings, ytdlp_version=ytdlp_version,
                                               ffmpeg_description=ffmpeg_description, parent=self)
        self.download_page.browse_requested.connect(lambda: self.dialogs.pick_directory(
            '选择下载目录', self.download_page.state['directory'], lambda value: self.download_page.setField('directory', value)))
        self.settings_page.browse_requested.connect(self._browse_setting)
        QQuickWindow.setTextRenderType(QQuickWindow.TextRenderType.QtTextRendering)
        if QQuickStyle.name() != 'Basic':
            QQuickStyle.setStyle('Basic')
        self.engine = QQmlApplicationEngine(self)
        self._disposed = False
        self.qml_warnings = []
        self.engine.warnings.connect(self._qml_warning)
        self.engine.addImageProvider('thumbnails', self.images)
        context = self.engine.rootContext()
        for name, value in (('shell', self), ('theme', self.theme), ('download', self.download_page),
                            ('history', self.history_page), ('settings', self.settings_page), ('dialogs', self.dialogs)):
            context.setContextProperty(name, value)
        context.setContextProperty('assetsBase', QUrl.fromLocalFile(str(resource_path('assets')) + '/'))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'Main.qml')))
        if not self.engine.rootObjects():
            raise RuntimeError('无法加载界面：' + '\n'.join(self.qml_warnings))
        self.root = self.engine.rootObjects()[0]
        # Basic controls finish their native font initialization after the
        # component tree is loaded; apply the fallback stack after that pass.
        QTimer.singleShot(80, self._apply_qml_typography)
        self.root.setIcon(QIcon(str(resource_path('assets', 'app.ico'))))

    def _apply_qml_typography(self):
        if self._disposed:
            return
        try:
            field = self.root.findChild(QObject, 'urlInput')
        except RuntimeError:
            return
        if field is not None:
            try:
                self.theme.applyFont(field, 'Body', field.property('text') or field.property('placeholderText'))
            except RuntimeError:
                return

    def dispose(self):
        # Destroy the QML object tree while all context objects are still alive.
        if not self._disposed:
            import shiboken6
            self._disposed = True
            self.root.hide()
            self.history_page.close()
            shiboken6.delete(self.engine)

    def _cover_busy(self):
        return any(getattr(session, '_workers', None) for session in self.dialogs.sessions)

    def _qml_warning(self, errors):
        for error in errors:
            message = error.toString()
            self.qml_warnings.append(message)
            logging.getLogger(__name__).warning('QML: %s', message)

    def _browse_setting(self, name):
        if name in {'download_directory', 'ffmpeg_directory'}:
            self.dialogs.pick_directory('选择目录', self.settings_page.state[name],
                                         lambda value: self.settings_page.edit(name, value))

    @Slot(int)
    def _select_page(self, index):
        if 0 <= index < 4:
            self.update(page=index)

    def apply_theme(self, _theme):
        # QML consumes the single semantic palette directly.
        pass

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def close(self):
        self.root.close()

    def grab(self):
        return self.root.grabWindow()

    def isVisible(self):
        return self.root.isVisible()

    def show_update_available(self, version):
        self.update(updateVisible=True, updateText=f'YT Downloader {version} 已可用')

    @Slot()
    def hideUpdate(self):
        self.update(updateVisible=False)

    def set_download_busy(self, busy):
        self._busy = busy
        self._finish_close()

    def set_update_busy(self, busy):
        self._update_busy = busy
        self._finish_close()

    def set_reduce_motion(self, enabled):
        self.update(reduceMotion=bool(enabled))

    @Slot()
    def requestClose(self):
        if not self._busy and not self._update_busy and not self._cover_busy():
            self.update(allowClose=True)
            QTimer.singleShot(0, self.root.close)
            return
        if self._confirming_close:
            return
        self._confirming_close = True
        self.dialogs.confirm('后台任务仍在进行', '仍有下载、封面或更新任务。你可以继续等待，或取消任务后退出。',
                             '取消任务并退出', self._close_answer, cancel='继续等待')

    def _close_answer(self, accepted):
        self._confirming_close = False
        if accepted:
            self._closing_after_cancel = True
            if self._busy:
                self.cancel_all_requested.emit()
            if self._update_busy:
                self.cancel_update_requested.emit()
            for session in tuple(self.dialogs.sessions):
                if session.state['kind'] == 'cover':
                    session.reject()
            self.hide()
            self._finish_close()

    def _finish_close(self):
        if not self._busy and not self._update_busy and not self._cover_busy() and self._closing_after_cancel:
            self._closing_after_cancel = False
            self.update(allowClose=True)
            self.root.close()

    @Slot()
    def openProject(self):
        if QDesktopServices.openUrl(QUrl(PROJECT_URL)):
            self.update(projectError='')
        else:
            self.update(projectError=f'无法打开默认浏览器。你可以复制此地址：{PROJECT_URL}')

    @Slot()
    def copyProject(self):
        QGuiApplication.clipboard().setText(PROJECT_URL)

    def scroll_download_to_top(self):
        self.scrollToTopRequested.emit()

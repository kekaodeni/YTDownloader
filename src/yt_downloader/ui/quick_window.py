"""Qt Quick shell and the application-facing presentation ports."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQuick import QQuickWindow

from yt_downloader import __version__
from yt_downloader.infrastructure.runtime import resource_path
from yt_downloader.ui.quick_dialogs import DialogBridge
from yt_downloader.ui.quick_download import DownloadPresenter
from yt_downloader.ui.quick_toolbox import ToolboxPresenter
from yt_downloader.ui.quick_browser_companion import BrowserCompanionPresenter
from yt_downloader.ui.quick_history import HistoryPresenter
from yt_downloader.ui.quick_images import ImageStore
from yt_downloader.ui.quick_settings import SettingsPresenter
from yt_downloader.ui.quick_state import ViewState
from yt_downloader.ui.quick_theme import QuickTheme
from yt_downloader.ui.quick_cookies import CookiePresenter
from yt_downloader.ui.localization import Translator

PROJECT_URL = 'https://github.com/kekaodeni/YTDownloader'


class MainWindow(ViewState):
    recovery_details_requested = Signal()
    cancel_all_requested = Signal()
    cancel_update_requested = Signal()
    show_update_requested = Signal()
    check_update_requested = Signal()
    scrollToTopRequested = Signal()

    def __init__(self, settings, *, ytdlp_version, ffmpeg_description, theme=None, icons=None):
        super().__init__(None, page=0, reduceMotion=settings.reduce_motion, allowClose=False,
                         updateVisible=False, updateText='', version=__version__, projectError='',
                         recoveryVisible=False, recoveryBusy=False, recoveryText='', updateStatus='尚未检查', updateChecking=False, updateAction='检查更新', updateReview=False)
        self.update(notificationVisible=False, notificationTitle='', notificationBody='')
        self._notification_timer = QTimer(self)
        self._notification_timer.setSingleShot(True)
        self._notification_timer.timeout.connect(lambda: self.update(notificationVisible=False))
        self._busy = False
        self._update_busy = False
        self._closing_after_cancel = False
        self._confirming_close = False
        self.theme = theme or QuickTheme(QGuiApplication.instance())
        self.i18n = Translator(settings.language, self)
        self._recovery_text_source = ''
        self._update_status_source = '尚未检查'
        self._update_ready = False
        self._update_banner_version = ''
        self._project_error_source = ''
        self.i18n.languageChanged.connect(self._refresh_localized_shell)
        self._refresh_localized_shell()
        self.images = ImageStore()
        self.dialogs = DialogBridge(self, self.i18n)
        self.cookies = CookiePresenter(self, translator=self.i18n)
        self.dialogs.sessionsChanged.connect(self._finish_close)
        self.download_page = DownloadPresenter(settings.download_directory, self.images, self, translator=self.i18n)
        self.toolbox_page = ToolboxPresenter(settings.download_directory, self.images, self, translator=self.i18n)
        self.browser_companion = BrowserCompanionPresenter(self.i18n, self)
        self.history_page = HistoryPresenter(self.dialogs, self, self.i18n)
        self.i18n.languageChanged.connect(self.history_page.refresh_localized)
        self.settings_page = SettingsPresenter(settings, ytdlp_version=ytdlp_version,
                                               ffmpeg_description=ffmpeg_description, translator=self.i18n, parent=self)
        self.settings_page.language_changed.connect(self.i18n.setLanguage)
        self.settings_page.changed.connect(self._sync_motion)
        self.cookies.editor_requested.connect(self._open_cookie_editor)
        self.cookies.profiles_changed.connect(self._sync_cookie_state)
        self.download_page.browse_requested.connect(lambda: self.dialogs.pick_directory(
            '选择下载目录', self.download_page.state['directory'], lambda value: self.download_page.setField('directory', value)))
        self.toolbox_page.browse_requested.connect(lambda: self.dialogs.pick_directory(
            '选择下载目录', self.toolbox_page.state['directory'], lambda value: self.toolbox_page.setField('directory', value)))
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
                            ('toolbox', self.toolbox_page),
                            ('browserCompanion', self.browser_companion),
                            ('history', self.history_page), ('settings', self.settings_page), ('dialogs', self.dialogs), ('cookies', self.cookies), ('i18n', self.i18n)):
            context.setContextProperty(name, value)
        context.setContextProperty('assetsBase', QUrl.fromLocalFile(str(resource_path('assets')) + '/'))
        motion_component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'MotionTokens.qml')))
        self.motion = motion_component.create(context)
        if self.motion is None:
            raise RuntimeError('\n'.join(error.toString() for error in motion_component.errors()))
        self.motion.setParent(self.engine)
        context.setContextProperty('motion', self.motion)
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'Main.qml')))
        if not self.engine.rootObjects():
            raise RuntimeError('无法加载界面：' + '\n'.join(self.qml_warnings))
        self.root = self.engine.rootObjects()[0]
        self.cookies.pickRequested.connect(self._open_cookie_picker)
        # Basic controls finish their native font initialization after the
        # component tree is loaded; apply the fallback stack after that pass.
        QTimer.singleShot(80, self._apply_qml_typography)
        self.root.setIcon(QIcon(str(resource_path('assets', 'app.ico'))))

    def _sync_cookie_state(self, _value=None):
        self.download_page.set_cookie_state(self.cookies.profiles)
        self.toolbox_page.set_cookie_state(self.cookies.profiles)

    @Slot()
    def _sync_motion(self):
        self.set_reduce_motion(self.settings_page.state['reduce_motion'])

    def _open_cookie_editor(self, profile):
        def save(values, session):
            saved = self.cookies.saveEditor(values)
            if not saved:
                session.update(message=self.cookies.state['message'])
            return saved
        def test(session):
            source = session.state['source']
            browser = session.state['browser']
            path = session.state['filePath']
            if source == 'file':
                from yt_downloader.services.cookie_service import cookie_options
                from yt_downloader.core.models import CookieProfile
                try:
                    cookie_options(CookieProfile('test', 'test', 'file', cookie_file=path))
                    session.update(message='Cookie 文件格式有效；开启后可用于解析和下载。')
                except ValueError as error:
                    session.update(message=str(error))
            else:
                session.update(message='将使用当前浏览器的登录状态；开启后在解析和下载时读取。')
        self.cookies._editor_session = self.dialogs.cookie_editor(
            profile, save, test, lambda: self.cookies.pickRequested.emit())

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

    @Slot()
    def openCookieSettings(self):
        self.settings_page.selectCategory(2)
        self._select_page(3)

    @Slot()
    def _open_cookie_picker(self):
        if self._disposed:
            return
        picker = self.root.findChild(QObject, 'cookiePicker')
        if picker is not None:
            picker.open()

    def dispose(self):
        # Destroy the QML object tree while all context objects are still alive.
        if not self._disposed:
            import shiboken6
            self._disposed = True
            self.root.hide()
            self.browser_companion.close()
            self.history_page.close()
            self.settings_page.close_tools()
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
        if 0 <= index < 5:
            self.update(page=index)

    def apply_theme(self, _theme):
        # QML consumes the single semantic palette directly.
        pass

    def show(self):
        self.root.show()

    def show_notification(self, title, body):
        self.update(notificationVisible=True, notificationTitle=title, notificationBody=body)
        self._notification_timer.start(4500)

    def hide(self):
        self.root.hide()

    def close(self):
        self.root.close()

    def grab(self):
        return self.root.grabWindow()

    def isVisible(self):
        return self.root.isVisible()

    def show_update_available(self, version):
        self._update_banner_version = str(version)
        self.update(updateVisible=True, updateText=self.i18n.text('update.available_banner', {'version': version}))

    def set_update_state(self, text, *, busy=False, review=False, ready=False):
        self._update_status_source = str(text)
        self._update_ready = bool(ready)
        self.update(updateChecking=busy, updateReview=review)
        self._refresh_localized_shell()

    def set_recovery_text(self, text, **values):
        self._recovery_text_source = str(text)
        self.update(recoveryText=self.i18n.sourceText(self._recovery_text_source), **values)

    def _refresh_localized_shell(self, _locale=None):
        if hasattr(self, 'i18n'):
            self.update(notificationVisible=False, updateStatus=self.i18n.sourceText(self._update_status_source),
                        updateAction=self.i18n.text('update.action_pending' if self._update_ready
                                                    else 'update.action_progress' if self._state['updateReview']
                                                    else 'update.action_check'),
                        projectError=self.i18n.sourceText(self._project_error_source),
                        recoveryText=self.i18n.sourceText(self._recovery_text_source),
                        updateText=(self.i18n.text('update.available_banner', {'version': self._update_banner_version})
                                    if self._update_banner_version else self._state['updateText']))

    @Slot()
    def updateAction(self):
        if self._state['updateChecking']:
            return
        if self._state['updateReview']:
            self.show_update_requested.emit()
        else:
            self.check_update_requested.emit()

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
        if self._state['recoveryBusy']:
            return
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
            self._project_error_source = ''
            self.update(projectError='')
        else:
            self._project_error_source = f'无法打开默认浏览器。你可以复制此地址：{PROJECT_URL}'
            self.update(projectError=self.i18n.sourceText(self._project_error_source))

    @Slot()
    def copyProject(self):
        QGuiApplication.clipboard().setText(PROJECT_URL)

    def scroll_download_to_top(self):
        self.scrollToTopRequested.emit()

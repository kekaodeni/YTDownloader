"""The existing settings editor's autosave and preview contract, without widgets."""
from dataclasses import asdict

from PySide6.QtCore import QTimer, Signal, Slot

from yt_downloader import __version__
from yt_downloader.core.models import AppSettings, CodecPreference
from yt_downloader.ui.quick_state import ViewState


class SettingsPresenter(ViewState):
    save_requested = Signal(object)
    network_test_requested = Signal(str, str)
    theme_preview_requested = Signal(str)
    open_logs_requested = Signal()
    copy_system_info_requested = Signal()
    browse_requested = Signal(str)

    def __init__(self, settings, *, ytdlp_version, ffmpeg_description, parent=None):
        values = asdict(settings)
        values['codec_preference'] = settings.codec_preference.value
        super().__init__(parent, **values, version=__version__, ytdlpVersion=ytdlp_version,
                         ffmpegDescription=ffmpeg_description, saveVisible=False, saveText='',
                         networkBusy=False, networkText='', networkSuccess=False)
        self._saved = settings
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self.save)
        self._status_hide_timer = QTimer(self)
        self._status_hide_timer.setSingleShot(True)
        self._status_hide_timer.setInterval(1800)
        self._status_hide_timer.timeout.connect(lambda: self.update(saveVisible=False))

    @Slot(str, 'QVariant')
    def edit(self, name, value):
        editable = {'download_directory', 'default_quality', 'theme', 'reduce_motion', 'ffmpeg_directory',
                    'max_concurrent_downloads', 'proxy_mode', 'custom_proxy_url', 'concurrent_fragments', 'codec_preference', 'auto_check_updates'}
        if name not in editable or self._state[name] == value:
            return
        self.update(**{name: value})
        if name == 'proxy_mode':
            self.update(networkText='')
        self._status_hide_timer.stop()
        self.update(saveVisible=True, saveText='有未保存的更改')
        immediate = name not in {'download_directory', 'custom_proxy_url', 'ffmpeg_directory'}
        self._autosave_timer.start(0 if immediate else 500)
        if name == 'theme':
            self.theme_preview_requested.emit(value)

    def current_settings(self):
        v = self._state
        return AppSettings(schema_version=5, download_directory=v['download_directory'].strip(),
                           default_quality=str(v['default_quality']), theme=str(v['theme']),
                           reduce_motion=bool(v['reduce_motion']), ffmpeg_directory=v['ffmpeg_directory'].strip(),
                           proxy_mode=str(v['proxy_mode']), custom_proxy_url=v['custom_proxy_url'].strip(),
                           concurrent_fragments=int(v['concurrent_fragments']),
                           max_concurrent_downloads=int(v['max_concurrent_downloads']),
                           codec_preference=CodecPreference(v['codec_preference']), auto_check_updates=bool(v['auto_check_updates']),
                           use_cookies=bool(v['use_cookies']))

    @Slot()
    def save(self):
        self._autosave_timer.stop()
        self._status_hide_timer.stop()
        self.update(saveVisible=True, saveText='正在保存…')
        self.save_requested.emit(self.current_settings())

    def mark_saved(self, settings):
        self._saved = settings
        self.update(saveVisible=True, saveText='已保存')
        self._status_hide_timer.start()

    def mark_save_failed(self, message):
        self._status_hide_timer.stop()
        self.update(saveVisible=True, saveText=f'无法保存：{message}')

    @Slot()
    def testNetwork(self):
        if self._state['networkBusy']:
            return
        self.set_network_test_busy(True)
        self.network_test_requested.emit(self._state['proxy_mode'], self._state['custom_proxy_url'].strip())

    def set_network_test_busy(self, busy):
        self.update(networkBusy=busy)
        if busy:
            self.update(networkText='正在使用当前设置测试连接…')

    def set_network_test_result(self, success, message):
        self.set_network_test_busy(False)
        self.update(networkSuccess=success, networkText=message)

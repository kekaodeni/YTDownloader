"""The existing settings editor's autosave and preview contract, without widgets."""
from dataclasses import asdict
import re
import uuid

from PySide6.QtCore import QProcess, QTimer, Signal, Slot

from yt_downloader import __version__
from yt_downloader.core.models import AppSettings, DownloadProfile
from yt_downloader.services.download_profiles import BUILTIN_PROFILES, profile_from_mapping
from yt_downloader.ui.quick_state import ViewState


class SettingsPresenter(ViewState):
    _component_versions = {}
    save_requested = Signal(object)
    network_test_requested = Signal(str, str)
    theme_preview_requested = Signal(str)
    open_logs_requested = Signal()
    copy_system_info_requested = Signal()
    browse_requested = Signal(str)
    language_changed = Signal(str)

    def __init__(self, settings, *, ytdlp_version, ffmpeg_description, translator=None, parent=None):
        values = asdict(settings)
        values.pop('default_download_profile_id', None)
        values.pop('custom_download_profiles', None)
        custom_profiles = tuple(settings.custom_download_profiles)
        super().__init__(parent, **values, version=__version__, ytdlpVersion=ytdlp_version,
                         profileOptions=[], customProfiles=[],
                         defaultProfileId=settings.default_download_profile_id,
                         profileEditorOpen=False, profileEditorMode='new', profileEditorId='',
                         profileDraftName='', profileDraftContentMode='video_audio',
                         profileDraftQuality='recommended', profileDraftCodec='auto',
                         profileDraftAudioCodec='original', profileDraftAudioQuality='original',
                         profileDraftSubtitleEnabled=False, profileDraftSubtitleAuto=False,
                         profileDraftSubtitleEmbed=False, profileDraftSubtitleFormat='srt',
                         profileDraftSubtitleLanguages=[], profileMessage='',
                         ffmpegDescription=ffmpeg_description, saveVisible=False, saveText='',
                         networkBusy=False, networkText='', networkSuccess=False, category=0)
        self._tool_process = None
        self._refresh_tools()
        self._translator = translator
        self._save_message_id = ''
        self._save_error = ''
        self._network_source = ''
        self._profile_message_source = ''
        self._saved = settings
        self._custom_profiles = custom_profiles
        self._profile_draft = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self.save)
        self._status_hide_timer = QTimer(self)
        self._status_hide_timer.setSingleShot(True)
        self._status_hide_timer.setInterval(1800)
        self._status_hide_timer.timeout.connect(lambda: self.update(saveVisible=False))
        self._sync_profiles()

        if translator is not None:
            translator.languageChanged.connect(self._refresh_localized)

    def _t(self, message_id, parameters=None):
        return self._translator.text(message_id, parameters) if self._translator else message_id

    def _localize_network_message(self, source):
        if self._translator is None:
            return source
        matched = re.fullmatch(r'连接成功（([^）]+) 秒） · (.*)', str(source), re.DOTALL)
        if matched:
            return self._translator.text('settings.network_test_success', {
                'seconds': matched.group(1),
                'description': self._translator.sourceText(matched.group(2)),
            })
        return self._translator.sourceText(source)

    @Slot(str)
    def _refresh_localized(self, _locale=None):
        self._sync_profiles()
        if self._save_message_id:
            params = {'message': self._save_error} if self._save_message_id == 'settings.save_failed' else None
            self.update(saveText=self._t(self._save_message_id, params))
        if self._state['networkBusy']:
            self.update(networkText=self._t('settings.network_testing'))
        elif self._network_source and self._translator is not None:
            self.update(networkText=self._localize_network_message(self._network_source))
        if self._profile_message_source and self._translator is not None:
            self.update(profileMessage=self._translator.sourceText(self._profile_message_source))

    @Slot(str, 'QVariant')
    def edit(self, name, value):
        editable = {'download_directory', 'theme', 'reduce_motion', 'ffmpeg_directory',
                    'max_concurrent_downloads', 'proxy_mode', 'custom_proxy_url', 'concurrent_fragments', 'auto_check_updates', 'language'}
        if name not in editable or self._state[name] == value:
            return
        self.update(**{name: value})
        if name == 'proxy_mode':
            self._network_source = ''
            self.update(networkText='')
        self._status_hide_timer.stop()
        self._set_save_message('settings.unsaved')
        immediate = name not in {'download_directory', 'custom_proxy_url', 'ffmpeg_directory'}
        self._autosave_timer.start(0 if immediate else 500)
        if name == 'theme':
            self.theme_preview_requested.emit(value)
        elif name == 'language':
            self.language_changed.emit(str(value))

    @Slot(str, 'QVariant')
    def setSetting(self, name, value):
        """QML-facing settings mutation entry point."""
        self.edit(name, value)

    @Slot(int)
    def selectCategory(self, index):
        if 0 <= index < 6:
            self.update(category=index)

    def current_settings(self):
        v = self._state
        return AppSettings(schema_version=7, download_directory=v['download_directory'].strip(),
                           theme=str(v['theme']),
                           reduce_motion=bool(v['reduce_motion']), ffmpeg_directory=v['ffmpeg_directory'].strip(),
                           proxy_mode=str(v['proxy_mode']), custom_proxy_url=v['custom_proxy_url'].strip(),
                           concurrent_fragments=int(v['concurrent_fragments']),
                           max_concurrent_downloads=int(v['max_concurrent_downloads']),
                           auto_check_updates=bool(v['auto_check_updates']), use_cookies=bool(v['use_cookies']),
                           default_download_profile_id=str(v['defaultProfileId']),
                           custom_download_profiles=self._custom_profiles,
                           language=str(v['language']))

    def _profile_option(self, profile, builtin):
        content = self._t({'video_audio': 'settings.content_video_audio',
                           'video_only': 'settings.content_video',
                           'audio_only': 'settings.content_audio'}[profile.content_mode])
        quality = {'recommended': self._t('settings.quality_recommended'),
                   'highest': self._t('settings.quality_highest')}.get(profile.quality_tier, profile.quality_tier)
        codec = {'auto': self._t('settings.codec_auto'), 'av1': 'AV1', 'vp9': 'VP9', 'h264': 'H.264'}[profile.codec_preference]
        subtitle = ' · ' + self._t('settings.subtitle_download') if profile.subtitle_enabled else ''
        name = profile.name
        if builtin and profile.id in {'auto', 'best'}:
            name = self._t('settings.quality_recommended' if profile.id == 'auto' else 'settings.quality_highest')
        return {**asdict(profile), 'name': name, 'builtin': builtin,
                'summary': f'{content} · {quality} · {codec}{subtitle}'}

    def _sync_profiles(self):
        options = [self._profile_option(profile, True) for profile in BUILTIN_PROFILES]
        options.extend(self._profile_option(profile, False) for profile in self._custom_profiles)
        self.update(profileOptions=options,
                    customProfiles=[self._profile_option(profile, False) for profile in self._custom_profiles])

    def _schedule_save(self):
        self._status_hide_timer.stop()
        self._set_save_message('settings.unsaved')
        self._autosave_timer.start(0)

    def _set_save_message(self, message_id, *, error=''):
        self._save_message_id = message_id
        self._save_error = error
        params = {'message': error} if message_id == 'settings.save_failed' else None
        self.update(saveVisible=True, saveText=self._t(message_id, params))

    @Slot(str)
    def setDefaultProfile(self, profile_id):
        available = {'auto', 'best', *(profile.id for profile in self._custom_profiles)}
        if profile_id not in available or profile_id == self._state['defaultProfileId']:
            return
        self.update(defaultProfileId=profile_id)
        self._schedule_save()

    @Slot()
    def newProfile(self):
        self._profile_draft = {
            'id': 'p-' + uuid.uuid4().hex,
            'name': '',
            'content_mode': 'video_audio',
            'quality_tier': 'recommended',
            'codec_preference': 'auto',
            'audio_codec': 'original',
            'audio_quality': 'original',
            'subtitle_enabled': False,
            'subtitle_auto': False,
            'subtitle_embed': False,
            'subtitle_format': 'srt',
            'subtitle_languages': (),
        }
        self._show_profile_editor('new')

    @Slot(str)
    def editProfile(self, profile_id):
        profile = next((item for item in self._custom_profiles if item.id == profile_id), None)
        if profile is None:
            return
        self._profile_draft = asdict(profile)
        self._show_profile_editor('edit')

    def _show_profile_editor(self, mode):
        draft = self._profile_draft
        self.update(profileEditorMode=mode, profileEditorId=draft['id'],
                    profileDraftName=draft['name'], profileDraftContentMode=draft['content_mode'],
                    profileDraftQuality=draft['quality_tier'], profileDraftCodec=draft['codec_preference'],
                    profileDraftAudioCodec=draft['audio_codec'], profileDraftAudioQuality=draft['audio_quality'],
                    profileDraftSubtitleEnabled=draft['subtitle_enabled'], profileDraftSubtitleAuto=draft['subtitle_auto'],
                    profileDraftSubtitleEmbed=draft['subtitle_embed'], profileDraftSubtitleFormat=draft['subtitle_format'],
                    profileDraftSubtitleLanguages=list(draft['subtitle_languages']),
                    profileEditorOpen=True, profileMessage='')

    @Slot(str, 'QVariant')
    def editProfileField(self, name, value):
        allowed = {'name', 'content_mode', 'quality_tier', 'codec_preference', 'audio_codec',
                   'audio_quality', 'subtitle_enabled', 'subtitle_auto', 'subtitle_embed',
                   'subtitle_format', 'subtitle_languages'}
        if self._profile_draft is None or name not in allowed:
            return
        if name == 'name':
            value = str(value)
        elif name == 'subtitle_languages':
            value = tuple(value)
        self._profile_draft[name] = value
        state_key = {'name': 'profileDraftName', 'content_mode': 'profileDraftContentMode',
                     'quality_tier': 'profileDraftQuality', 'codec_preference': 'profileDraftCodec',
                     'audio_codec': 'profileDraftAudioCodec', 'audio_quality': 'profileDraftAudioQuality',
                     'subtitle_enabled': 'profileDraftSubtitleEnabled', 'subtitle_auto': 'profileDraftSubtitleAuto',
                     'subtitle_embed': 'profileDraftSubtitleEmbed', 'subtitle_format': 'profileDraftSubtitleFormat',
                     'subtitle_languages': 'profileDraftSubtitleLanguages'}[name]
        self.update(**{state_key: list(value) if name == 'subtitle_languages' else value}, profileMessage='')
        self._profile_message_source = ''

    @Slot()
    def saveProfile(self):
        if self._profile_draft is None:
            return
        try:
            profile = profile_from_mapping(self._profile_draft)
            if any(existing.id != profile.id and existing.name.casefold() == profile.name.casefold()
                   for existing in self._custom_profiles):
                raise ValueError('已有同名的自定义预设。')
        except (TypeError, ValueError) as error:
            message = str(error)
            self._profile_message_source = message
            if self._translator is not None:
                message = self._translator.sourceText(message)
            self.update(profileMessage=message)
            return
        updated = list(self._custom_profiles)
        index = next((i for i, item in enumerate(updated) if item.id == profile.id), None)
        if index is None:
            updated.append(profile)
        else:
            updated[index] = profile
        self._custom_profiles = tuple(updated)
        self._profile_draft = None
        self._profile_message_source = ''
        self.update(profileEditorOpen=False)
        self._sync_profiles()
        self._schedule_save()

    @Slot(str)
    def deleteProfile(self, profile_id):
        if not any(item.id == profile_id for item in self._custom_profiles):
            return
        self._custom_profiles = tuple(item for item in self._custom_profiles if item.id != profile_id)
        if self._state['defaultProfileId'] == profile_id:
            self.update(defaultProfileId='auto')
        self._sync_profiles()
        self._schedule_save()

    @Slot()
    def closeProfileEditor(self):
        self._profile_draft = None
        self._profile_message_source = ''
        self.update(profileEditorOpen=False, profileMessage='')

    @Slot()
    def save(self):
        self._autosave_timer.stop()
        self._status_hide_timer.stop()
        self._set_save_message('settings.saving')
        self.save_requested.emit(self.current_settings())

    def mark_saved(self, settings):
        self._saved = settings
        self._refresh_tools()
        self._set_save_message('settings.saved')
        self._status_hide_timer.start()

    def _refresh_tools(self):
        from yt_downloader.services.ffmpeg_service import FfmpegService
        tool = FfmpegService(configured_directory=self._state['ffmpeg_directory'] or None).ffmpeg_path
        self.update(ffmpegPath=str(tool or ''), ffmpegVersion='')
        self.close_tools()
        if tool is None:
            return
        try:
            stamp = tool.stat()
        except OSError:
            return
        key = (str(tool), stamp.st_mtime_ns, stamp.st_size)
        cached = self._component_versions.get(key)
        if cached:
            self.update(ffmpegVersion=cached)
            return
        process = QProcess(self)
        self._tool_process = process
        def finished(_code, _status):
            if process is not self._tool_process:
                return
            output = bytes(process.readAllStandardOutput()).decode('utf-8', 'replace')
            match = re.search(r'^ffmpeg version\s+(\S+)', output)
            if match:
                self._component_versions[key] = match.group(1)
                self.update(ffmpegVersion=match.group(1))
        process.finished.connect(finished)
        process.start(str(tool), ['-version'])

    def close_tools(self):
        process, self._tool_process = self._tool_process, None
        if process is not None:
            if process.state() != QProcess.NotRunning:
                process.kill()
                process.waitForFinished(1000)
            process.deleteLater()

    def mark_save_failed(self, message):
        self._status_hide_timer.stop()
        self._set_save_message('settings.save_failed', error=str(message))

    @Slot()
    def testNetwork(self):
        if self._state['networkBusy']:
            return
        self.set_network_test_busy(True)
        self.network_test_requested.emit(self._state['proxy_mode'], self._state['custom_proxy_url'].strip())

    def set_network_test_busy(self, busy):
        self.update(networkBusy=busy)
        if busy:
            self.update(networkText=self._t('settings.network_testing'))

    def set_network_test_result(self, success, message):
        self.set_network_test_busy(False)
        self._network_source = str(message)
        localized = self._localize_network_message(self._network_source)
        self.update(networkSuccess=success, networkText=localized)

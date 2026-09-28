"""The existing settings editor's autosave and preview contract, without widgets."""
from dataclasses import asdict
import uuid

from PySide6.QtCore import QTimer, Signal, Slot

from yt_downloader import __version__
from yt_downloader.core.models import AppSettings, DownloadProfile
from yt_downloader.services.download_profiles import BUILTIN_PROFILES, profile_from_mapping
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
        values.pop('default_download_profile_id', None)
        values.pop('custom_download_profiles', None)
        custom_profiles = tuple(settings.custom_download_profiles)
        profile_options = [self._profile_option(profile, builtin=True) for profile in BUILTIN_PROFILES]
        profile_options.extend(self._profile_option(profile, builtin=False) for profile in custom_profiles)
        super().__init__(parent, **values, version=__version__, ytdlpVersion=ytdlp_version,
                         profileOptions=profile_options, customProfiles=[self._profile_option(p, False) for p in custom_profiles],
                         defaultProfileId=settings.default_download_profile_id,
                         profileEditorOpen=False, profileEditorMode='new', profileEditorId='',
                         profileDraftName='', profileDraftContentMode='video_audio',
                         profileDraftQuality='recommended', profileDraftCodec='auto',
                         profileDraftAudioCodec='original', profileDraftAudioQuality='original',
                         profileDraftSubtitleEnabled=False, profileDraftSubtitleAuto=False,
                         profileDraftSubtitleEmbed=False, profileDraftSubtitleFormat='srt',
                         profileDraftSubtitleLanguages=[], profileMessage='',
                         ffmpegDescription=ffmpeg_description, saveVisible=False, saveText='',
                         networkBusy=False, networkText='', networkSuccess=False)
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

    @Slot(str, 'QVariant')
    def edit(self, name, value):
        editable = {'download_directory', 'theme', 'reduce_motion', 'ffmpeg_directory',
                    'max_concurrent_downloads', 'proxy_mode', 'custom_proxy_url', 'concurrent_fragments', 'auto_check_updates'}
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
        return AppSettings(schema_version=6, download_directory=v['download_directory'].strip(),
                           theme=str(v['theme']),
                           reduce_motion=bool(v['reduce_motion']), ffmpeg_directory=v['ffmpeg_directory'].strip(),
                           proxy_mode=str(v['proxy_mode']), custom_proxy_url=v['custom_proxy_url'].strip(),
                           concurrent_fragments=int(v['concurrent_fragments']),
                           max_concurrent_downloads=int(v['max_concurrent_downloads']),
                           auto_check_updates=bool(v['auto_check_updates']), use_cookies=bool(v['use_cookies']),
                           default_download_profile_id=str(v['defaultProfileId']),
                           custom_download_profiles=self._custom_profiles)

    @staticmethod
    def _profile_option(profile, builtin):
        content = {'video_audio': '视频 + 音频', 'video_only': '仅视频', 'audio_only': '仅音频'}[profile.content_mode]
        quality = {'recommended': '自动推荐', 'highest': '最高质量'}.get(profile.quality_tier, profile.quality_tier)
        codec = {'auto': '自动编码', 'av1': 'AV1', 'vp9': 'VP9', 'h264': 'H.264'}[profile.codec_preference]
        subtitle = ' · 下载字幕' if profile.subtitle_enabled else ''
        return {**asdict(profile), 'builtin': builtin,
                'summary': f'{content} · {quality} · {codec}{subtitle}'}

    def _sync_profiles(self):
        options = [self._profile_option(profile, True) for profile in BUILTIN_PROFILES]
        options.extend(self._profile_option(profile, False) for profile in self._custom_profiles)
        self.update(profileOptions=options,
                    customProfiles=[self._profile_option(profile, False) for profile in self._custom_profiles])

    def _schedule_save(self):
        self._status_hide_timer.stop()
        self.update(saveVisible=True, saveText='有未保存的更改')
        self._autosave_timer.start(0)

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
            self.update(profileMessage=str(error))
            return
        updated = list(self._custom_profiles)
        index = next((i for i, item in enumerate(updated) if item.id == profile.id), None)
        if index is None:
            updated.append(profile)
        else:
            updated[index] = profile
        self._custom_profiles = tuple(updated)
        self._profile_draft = None
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
        self.update(profileEditorOpen=False, profileMessage='')

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

"""Download presentation. Domain objects and command parameters stay in Python."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from yt_downloader.core.errors import CancellationCleanupReport
from yt_downloader.core.filename import sanitize_filename
from yt_downloader.core.formatting import format_bytes, format_duration, format_eta, format_speed
from yt_downloader.core.formats import apply_codec_preference
from yt_downloader.core.models import AuthState, CodecPreference, DownloadProgress, DownloadRequest, DownloadResult, ParseState, STATUS_TEXT, TASK_STATUS_MESSAGE_IDS, TaskStatus, VideoInfo
from yt_downloader.core.url import InvalidMediaUrl, normalize_media_url
from yt_downloader.ui.quick_state import RowModel, ViewState


_BATCH_QUALITY_MESSAGE_IDS = (
    'collection.quality.highest', 'collection.quality.cap2160',
    'collection.quality.cap1440', 'collection.quality.cap1080',
    'collection.quality.cap720',
)
_BATCH_QUALITY_TARGETS = ('highest', 'cap:2160p', 'cap:1440p', 'cap:1080p', 'cap:720p')


@dataclass
class TaskPresentation:
    request: DownloadRequest
    status: TaskStatus = TaskStatus.PENDING
    file_path: Path | None = None
    last_percent: int | None = None
    values: dict = field(default_factory=dict)

    def progress(self, progress: DownloadProgress):
        self.status = progress.status
        stopping = progress.status in {TaskStatus.CANCELLING, TaskStatus.CANCELLED, TaskStatus.FAILED}
        held = progress.status in {TaskStatus.PAUSING, TaskStatus.PAUSED, TaskStatus.RESUMING}
        downloading = progress.status in {TaskStatus.DOWNLOADING_VIDEO, TaskStatus.DOWNLOADING_AUDIO}
        values = dict(self.values)
        values.update(status=progress.status.value, statusKey=TASK_STATUS_MESSAGE_IDS[progress.status],
                      statusText=STATUS_TEXT[progress.status],
                      indeterminate=not stopping and not held and progress.percent is None,
                      speed='—' if stopping or held else format_speed(progress.speed),
                      eta='剩余 —' if stopping or held else f'剩余 {format_eta(progress.eta)}',
                      etaTime='—' if stopping or held else format_eta(progress.eta), etaTemplate='task.eta',
                      sizeTemplate='task.size',
                      retry=progress.status is TaskStatus.FAILED,
                      stopping=stopping or held,
                      pauseVisible=downloading or held or progress.status in {TaskStatus.MERGING, TaskStatus.POST_PROCESSING},
                      pauseEnabled=downloading, resumeEnabled=progress.status is TaskStatus.PAUSED,
                      pauseText='继续' if progress.status is TaskStatus.PAUSED else '正在暂停…' if progress.status is TaskStatus.PAUSING else '正在继续…' if progress.status is TaskStatus.RESUMING else '暂停')
        if not stopping and not held and progress.percent is not None:
            self.last_percent = round(progress.percent)
        values['percent'] = self.last_percent or 0
        values['percentText'] = f'{self.last_percent}%' if self.last_percent is not None and (stopping or held or progress.percent is not None) else '—%'
        if progress.resolved_quality:
            values['quality'] = progress.resolved_quality
        if (not stopping and not held) or progress.downloaded_bytes is not None or progress.total_bytes is not None:
            total = format_bytes(progress.total_bytes)
            if progress.total_is_estimate and progress.total_bytes is not None:
                total = f'估算 {total}'
            values['size'] = f'{format_bytes(progress.downloaded_bytes)} / {total}'
            values.update(sizeDownloaded=format_bytes(progress.downloaded_bytes),
                          sizeTotal=format_bytes(progress.total_bytes),
                          sizeEstimated=bool(progress.total_is_estimate and progress.total_bytes is not None))
        self.values = values


class DownloadPresenter(ViewState):
    collection_download_requested = Signal(object, object)
    parse_requested = Signal(str)
    parse_cancel_requested = Signal()
    download_requested = Signal(object, object, str, str)
    cancel_requested = Signal(str)
    pause_requested = Signal(str)
    resume_requested = Signal(str)
    open_file_requested = Signal(str)
    open_folder_requested = Signal(str)
    remove_requested = Signal(str)
    retry_requested = Signal(str)
    browse_requested = Signal()
    cookie_enabled_changed = Signal(bool)

    def __init__(self, directory: str, images, parent=None, translator=None):
        if translator is None:
            from yt_downloader.ui.localization import Translator
            translator = Translator('zh-CN', parent)
        super().__init__(parent, url='', filename='', directory=directory, ready=False,
                         busy=False, cancelling=False, parseText='解析', parseHint='',
                         clipboardHint='', title='', meta='', thumbnail='', formats=[],
                         formatIndex=0, qualityAuto=True, technical='', compatibilityHint='', mediaHint='',
                         mediaMode='video_audio', audioCodec='original', audioQuality='original',
                         modeHint='', subtitleEnabled=False, subtitleAuto=False,
                         advancedExpanded=False, clipEnabled=False, clipStart='00:00', clipEnd='',
                         clipError='', clipValid=True, embedThumbnail=False, embedMetadata=False,
                         embedChapters=False, remuxContainer='', sponsorblockMark=False, mediaSite='',
                         subtitleEmbed=False, subtitleFormat='srt', subtitleLanguages=[],
                         subtitleChoices=[], subtitleCapability='NONE', subtitleCanDownload=False,
                         subtitleCanAuto=False, subtitleCanFormat=False, subtitleCanEmbed=False,
                         subtitleHint='', subtitleAutoHint='', subtitleManualStatus='人工字幕：暂无',
                         subtitleAutoStatus='自动字幕：暂无', subtitleEmbedHint='',
                         playlist=False, selectedCount=0, playlistCount=0,
                         collection=False, collectionQuality='',
                         collectionQualityIndex=0, collectionQualityLabels=[],
                         collectionQualityTargets=[], collectionQualityMode='',
                         collectionKind='',
                         collectionSelectableCount=0, collectionSelectState=0,
                         cookieEnabled=False, cookieHint='', cookieAuthStatus='',
                         cookieAuthWarning='', cookieAuthInvalid=False, cookieAuthSeverity='')
        self._translator = translator
        self._cookie_status_key = ''
        self._cookie_status_params = {}
        self._cookie_warning_key = ''
        self._cookie_warning_params = {}
        self._cookie_warning_external = ''
        self._translated_state = {}
        self._format_option = None
        self._format_summary = ''
        self._format_size_key = ''
        self._format_size_params = {}
        self.images = images
        self.video: VideoInfo | None = None
        from yt_downloader.services.ffmpeg_service import FfmpegService
        self.subtitle_ffmpeg_available = FfmpegService().available
        self.parse_state = ParseState.IDLE
        self.cards: dict[str, TaskPresentation] = {}
        self._terminal_task_ids: set[str] = set()
        self._default_directory = directory
        self._directory_overridden = False
        self._tasks = RowModel(self)
        self._entries = RowModel(self)
        self._selected_entries = set()
        self._cookie_profiles = ()
        self._active_cookie_profile = None
        self._subtitle_preferences = {'enabled': False, 'auto': False, 'embed': False}
        if translator is not None:
            translator.languageChanged.connect(self._refresh_localized)
        self._set_text('parseText', 'download.parse')
        self._set_text('subtitleManualStatus', 'download.subtitle_manual_none')
        self._set_text('subtitleAutoStatus', 'download.subtitle_auto_none')

    def _set_text(self, field, message_id, parameters=None):
        if not message_id:
            self._translated_state.pop(field, None)
            self.update(**{field: ''})
            return
        self._translated_state[field] = (message_id, dict(parameters or {}))
        self.update(**{field: self._t(message_id, parameters)})

    def _t(self, key, params=None):
        return self._translator.text(key, params) if self._translator else key

    def _set_cookie_status(self, key='', params=None, *, warning_key='', warning_params=None,
                           warning_external='', invalid=False, severity=''):
        self._cookie_status_key = key
        self._cookie_status_params = dict(params or {})
        self._cookie_warning_key = warning_key
        self._cookie_warning_params = dict(warning_params or {})
        self._cookie_warning_external = warning_external
        self.update(cookieAuthStatus=self._t(key, self._cookie_status_params) if key else '',
                    cookieAuthWarning=(warning_external or self._t(warning_key, self._cookie_warning_params)) if warning_key or warning_external else '',
                    cookieAuthInvalid=invalid, cookieAuthSeverity=severity)

    def _refresh_localized(self, _locale=None):
        if self._translated_state:
            self.update(**{field: self._t(message_id, params)
                           for field, (message_id, params) in self._translated_state.items()})
        if self.video and self._state['collection']:
            self._refresh_collection_quality_targets()
            for index, entry in enumerate(self.video.entries):
                row = self._entries.get(index)
                if row:
                    self._entries.put(dict(row, detail=self._collection_entry_detail(entry)))
        if self._format_option is not None:
            self._format_summary = self._technical_summary(self._format_option)
        if self._format_summary or self._format_size_key:
            size_text = self._t(self._format_size_key, self._format_size_params) if self._format_size_key else ''
            self.update(technical=(self._format_summary + ('  ·  ' + size_text if size_text else '')).strip())
        if self._cookie_status_key or self._cookie_warning_key or self._cookie_warning_external:
            self.update(cookieAuthStatus=self._t(self._cookie_status_key, self._cookie_status_params) if self._cookie_status_key else '',
                        cookieAuthWarning=(self._cookie_warning_external or self._t(self._cookie_warning_key, self._cookie_warning_params)) if self._cookie_warning_key or self._cookie_warning_external else '')
        self._refresh_cookie_hint()

    def set_cookie_state(self, profiles, _legacy_default=None):
        changed = tuple(profiles) != self._cookie_profiles
        self._cookie_profiles = tuple(profiles)
        if changed and self.video is not None:
            self._invalidate_media()
        self._refresh_cookie_hint()

    def selected_cookie_profile(self, cookies):
        if not self._state['cookieEnabled']:
            return None
        if self.video is not None or self.parse_state in {ParseState.RUNNING, ParseState.SLOW}:
            return self._active_cookie_profile
        return self._cookie_route().profile

    def _cookie_route(self):
        from yt_downloader.services.cookie_service import route_cookie_profile
        return route_cookie_profile(self._cookie_profiles, self._state['url'])

    def _refresh_cookie_hint(self):
        route = None
        if not self._state['cookieEnabled'] or not self._state['url'].strip():
            hint = ''
            if self._cookie_status_key == 'download.cookie_pending':
                self._set_cookie_status()
        else:
            route = self._cookie_route()
            hint = (self._t('download.cookie_route_conflict') if route.status == 'conflict'
                    else self._t('download.cookie_route_missing') if route.status == 'missing' else '')
        if self._state['cookieEnabled'] and route and route.profile:
            site = self._cookie_site_name()
            if site and not self._cookie_status_key:
                self._set_cookie_status('download.cookie_pending', {'site': site}, severity='neutral')
        self.update(cookieHint=hint)

    def _cookie_site_name(self):
        from urllib.parse import urlsplit
        host = (urlsplit(self._state['url']).hostname or '').casefold().removeprefix('www.')
        if host == 'youtube.com' or host.endswith('.youtube.com') or host in {'youtu.be', 'youtube-nocookie.com'}:
            return 'YouTube'
        if host == 'bilibili.com' or host.endswith('.bilibili.com') or host in {'b23.tv', 'bili2233.cn'}:
            return 'Bilibili'
        return ''

    def set_cookie_parse_error(self, code, user_message=''):
        site = self._cookie_site_name()
        if not site:
            return
        if code in {'BROWSER_PROFILE_LOCKED', 'COOKIE_DECRYPT_FAILED', 'BROWSER_COOKIE_READ_FAILED'}:
            self._set_cookie_status('download.cookie_read_failed', {'site': site},
                                    warning_key='download.cookie_read_hint', warning_external=user_message,
                                    severity='error')
        elif code in {'COOKIE_REQUIRED', 'AUTH_REQUIRED'}:
            self._set_cookie_status('download.cookie_auth_required', {'site': site},
                                    warning_key='download.cookie_login_hint', warning_external=user_message,
                                    invalid=True, severity='error')

    def _invalidate_media(self):
        self.video = None
        self._active_cookie_profile = None
        self._format_summary = ''
        self._format_option = None
        self._format_size_key = ''
        self._format_size_params = {}
        self._selected_entries.clear()
        self._entries.replace([])
        self._set_cookie_status()
        self._set_text('meta', None)
        self.update(ready=False, title='', formats=[], technical='', collection=False, playlist=False,
                    selectedCount=0, playlistCount=0, collectionSelectableCount=0,
                    collectionSelectState=0)
        self._subtitle_state(reset_selection=True)

    @Slot(bool)
    def setCookieEnabled(self, enabled):
        enabled = bool(enabled)
        if self._state['cookieEnabled'] == enabled:
            return
        self.update(cookieEnabled=enabled)
        self._invalidate_media()
        self._refresh_cookie_hint()
        self.cookie_enabled_changed.emit(enabled)

    @Property(QObject, constant=True)
    def tasks(self):
        return self._tasks

    @Property(QObject, constant=True)
    def entries(self):
        return self._entries

    @Slot(int, bool)
    def selectEntry(self, index, selected):
        if not self.video or not 0 <= index < len(self.video.entries):
            return
        entry = self.video.entries[index]
        if entry.unavailable or (entry.embedded and not self._entry_options(entry)):
            return
        if selected:
            self._selected_entries.add(index)
        else:
            self._selected_entries.discard(index)
        row = self._entries.get(index)
        self._entries.put(dict(row, selected=selected))
        self.update(selectedCount=len(self._selected_entries))
        self._sync_collection_selection()

    def _entry_options(self, entry):
        mode = self._state['mediaMode']
        if mode == 'audio_only':
            options = entry.audio_formats
            codec = self._state['audioCodec']
            matching = tuple(option for option in options if
                             (codec == 'm4a' and option.acodec.startswith(('mp4a', 'aac'))) or
                             (codec == 'opus' and option.acodec == 'opus'))
            return matching or options
        if mode == 'video_only':
            return entry.video_only_formats
        return entry.formats

    @Slot(int, int)
    def selectEntryFormat(self, index, format_index):
        # Kept as a compatibility no-op for older QML references; collection
        # children intentionally share one quality target in the toolbar.
        return

    @Slot(bool)
    def selectAllEntries(self, selected):
        if self.video:
            selected = bool(selected)
            for index, entry in enumerate(self.video.entries):
                row = self._entries.get(index)
                if row.get('unavailable'):
                    continue
                if selected:
                    self._selected_entries.add(index)
                else:
                    self._selected_entries.discard(index)
                self._entries.put(dict(row, selected=selected))
            self.update(selectedCount=len(self._selected_entries))
            self._sync_collection_selection()

    def _sync_collection_selection(self):
        selectable = sum(not self._entries.get(i).get('unavailable') for i in range(self._entries.count))
        selected = len(self._selected_entries)
        state = 2 if selectable and selected == selectable else 1 if selected else 0
        self.update(collectionSelectableCount=selectable, collectionSelectState=state)

    def _refresh_collection_quality_targets(self):
        if not self.video or not self._state['collection']:
            return
        mode = str(self.video.collection_quality_mode or 'DEFERRED_BATCH_TARGET')
        if mode == 'RESOLVED_COMMON_FORMATS':
            entries = [entry for entry in self.video.entries if not entry.unavailable]
            options_by_entry = [self._entry_options(entry) for entry in entries]
            if options_by_entry and all(options_by_entry):
                common = set.intersection(*[{option.label for option in options} for options in options_by_entry])
                options = tuple(option for option in options_by_entry[0] if option.label in common)
            else:
                options = ()
            labels = list(dict.fromkeys(option.label for option in options))
            targets = labels
        else:
            labels = [self._t(message_id) for message_id in _BATCH_QUALITY_MESSAGE_IDS]
            targets = list(_BATCH_QUALITY_TARGETS)
        current = self._state['collectionQuality']
        if mode == 'RESOLVED_COMMON_FORMATS' and current not in targets:
            from yt_downloader.core.quality_target import choose_quality
            selected = choose_quality(options, current)
            current = selected.label if selected else (targets[0] if targets else '')
        elif current not in targets:
            current = 'highest' if mode == 'DEFERRED_BATCH_TARGET' else (targets[0] if targets else '')
        index = targets.index(current) if current in targets else 0
        self.update(collectionQualityMode=mode, collectionQualityLabels=labels,
                    collectionQualityTargets=targets, collectionQuality=current,
                    collectionQualityIndex=index)

    @Slot(int)
    def selectCollectionQuality(self, index):
        labels = self._state['collectionQualityLabels']
        targets = self._state['collectionQualityTargets']
        if not 0 <= index < len(labels) or index >= len(targets):
            return
        self.update(collectionQuality=targets[index], collectionQualityIndex=index)

    def set_clipboard_hint(self, text):
        try:
            normalized = normalize_media_url(text)
        except InvalidMediaUrl:
            self._set_text('clipboardHint', None)
            return
        self._set_text('clipboardHint', 'download.clipboard_hint', {'url': normalized})

    @Slot(str, 'QVariant')
    def setField(self, name, value):
        if name not in {'url', 'filename', 'directory'} or self._state[name] == value:
            return
        if name == 'directory':
            self._directory_overridden = True
        if name == 'url':
            self._invalidate_media()
        self.update(**{name: value})
        if name == 'url':
            self._refresh_cookie_hint()

    @Slot(str, bool)
    def setAdvancedToggle(self, name, value):
        fields = {
            'advancedExpanded': 'advancedExpanded',
            'clipEnabled': 'clipEnabled', 'embedThumbnail': 'embedThumbnail',
            'embedMetadata': 'embedMetadata', 'embedChapters': 'embedChapters',
            'sponsorblockMark': 'sponsorblockMark',
        }
        if name not in fields:
            return
        if name == 'clipEnabled' and self._state['collection']:
            self.update(clipEnabled=False)
            return
        self.update(**{fields[name]: value})
        if name == 'clipEnabled' or name in {'embedMetadata', 'embedChapters'}:
            self._validate_clip_state()

    @Slot(str, str)
    def setAdvancedField(self, name, value):
        if name in {'clipStart', 'clipEnd'}:
            self.update(**{name: value})
            self._validate_clip_state()
        elif name == 'remuxContainer' and value in {'', 'mp4', 'mkv', 'webm'}:
            self.update(remuxContainer=value)

    def _validate_clip_state(self):
        if not self._state['clipEnabled']:
            self.update(clipError='', clipValid=True)
            return
        if self.video is not None and self._state['collection']:
            self._set_text('clipError', 'clip.batch_unsupported')
            self.update(clipValid=False)
            return
        try:
            from yt_downloader.services.video_sections import parse_clip_time, validate_clip
            start = parse_clip_time(self._state['clipStart'])
            end = parse_clip_time(self._state['clipEnd'])
            validate_clip(True, start, end, self.video.duration if self.video else None)
        except ValueError as error:
            if 'duration' in str(error).lower():
                self._set_text('clipError', 'clip.end_after_duration')
            elif 'earlier' in str(error).lower():
                self._set_text('clipError', 'clip.start_before_end')
            else:
                self._set_text('clipError', 'clip.invalid_time')
            self.update(clipValid=False)
            return
        self._set_text('clipError', None)
        self.update(clipValid=True)

    def set_url(self, value):
        self.setField('url', value)

    @Slot()
    def requestParse(self):
        if self.parse_state in {ParseState.RUNNING, ParseState.SLOW}:
            self.set_parse_state(ParseState.CANCELLING)
            self.parse_cancel_requested.emit()
            return
        if self.parse_state is not ParseState.CANCELLING and self._state['url'].strip():
            if self._state['cookieEnabled'] and self._cookie_route().status == 'conflict':
                self._refresh_cookie_hint()
                return
            self._active_cookie_profile = self._cookie_route().profile if self._state['cookieEnabled'] else None
            site = self._cookie_site_name()
            if site and self._active_cookie_profile:
                self._set_cookie_status('download.cookie_pending', {'site': site}, severity='neutral')
            else:
                self._set_cookie_status()
            self.parse_requested.emit(self._state['url'].strip())

    def set_loading(self, loading):
        self.set_parse_state(ParseState.RUNNING if loading else ParseState.IDLE)

    def set_parse_state(self, state):
        self.parse_state = state
        if state is ParseState.RUNNING:
            self.video = None
            self.update(ready=False, thumbnail='')
            self._subtitle_state(reset_selection=True)
        busy = state in {ParseState.RUNNING, ParseState.SLOW, ParseState.CANCELLING}
        cancelling = state is ParseState.CANCELLING
        self.update(busy=busy, cancelling=cancelling)
        self._set_text('parseText', 'download.stop_parsing' if cancelling
                       else 'download.cancel_parse' if busy else 'download.parse')
        if state is ParseState.SLOW:
            self._set_text('parseHint', 'download.parse_slow')
        else:
            self._translated_state.pop('parseHint', None)
            self.update(parseHint='')

    def show_video(self, video, *, preferred_quality='recommended', profile=None):
        self.video = video
        self._format_codec_preference = CodecPreference(profile.codec_preference) if profile else CodecPreference.AUTO
        is_bilibili = str(video.extractor_key or '').casefold().startswith('bilibili')
        auth_state = (AuthState(video.auth_state)
                      if is_bilibili and self._state['cookieEnabled'] else AuthState.NOT_APPLICABLE)
        auth_messages = {
            AuthState.VALID: ('download.cookie_valid', '', 'success'),
            AuthState.INVALID: ('download.cookie_invalid', 'download.cookie_expired_hint', 'error'),
            AuthState.UNKNOWN: ('download.cookie_unknown', '', 'neutral'),
            AuthState.NOT_APPLICABLE: ('', '', ''),
        }
        auth_status_key, auth_warning_key, auth_severity = auth_messages[auth_state]
        auth_status_params = {}
        auth_warning_external = ''
        self._selected_entries.clear()
        is_playlist = video.is_collection
        self._entries.replace([dict(id=str(index), index=index, title=entry.title,
                                   url=entry.url, thumbnail=entry.thumbnail, unavailable=entry.unavailable,
                                   selected=False, embedded=entry.embedded,
                                   detail=self._collection_entry_detail(entry))
                              for index, entry in enumerate(video.entries)])
        self.update(playlist=is_playlist, collection=is_playlist, collectionKind=video.collection_kind,
                    mediaSite=('youtube' if str(video.extractor_key or '').casefold().startswith('youtube') else ''),
                    selectedCount=0,
                    playlistCount=len(video.entries), collectionQuality='',
                    collectionQualityLabels=[], collectionQualityTargets=[],
                    collectionQualityMode=str(video.collection_quality_mode or ''),
                    collectionQualityIndex=0)
        if is_playlist and self._state['clipEnabled']:
            self.update(clipEnabled=False)
            self._validate_clip_state()
        self._directory_overridden = False
        selected = 0
        labels = []
        for index, option in enumerate(video.formats):
            labels.append(self._t('download.recommended', {'label': option.label}) if option.is_recommended else option.label)
            if (preferred_quality == 'recommended' and option.is_recommended) or option.label == preferred_quality:
                selected = index
        if video.metadata_compatibility == 'VERIFIED' and video.download_compatibility == 'EXPERIMENTAL':
            compatibility_hint = self._t('download.compat_verified')
        elif video.download_compatibility == 'EXPERIMENTAL':
            compatibility_hint = self._t('download.compat_experimental')
        else:
            compatibility_hint = ''
        multi_video_hint = ''
        if (not is_bilibili and video.cookie_used and self._active_cookie_profile
                and self._cookie_site_name() == 'YouTube'):
            auth_status_key = 'download.cookie_used'
            auth_warning_key = ''
            auth_severity = 'success'
        self._set_cookie_status(auth_status_key, auth_status_params, warning_key=auth_warning_key,
                                warning_external=auth_warning_external,
                                invalid=auth_state is AuthState.INVALID, severity=auth_severity)
        self.update(technical='')
        self._set_text('compatibilityHint', 'download.compat_verified' if video.metadata_compatibility == 'VERIFIED' and video.download_compatibility == 'EXPERIMENTAL'
                       else 'download.compat_experimental' if video.download_compatibility == 'EXPERIMENTAL' else None)
        if is_playlist:
            self._set_text('mediaHint', 'collection.truncated' if video.entries_truncated else 'collection.guidance')
        else:
            self._translated_state.pop('mediaHint', None)
            self.update(mediaHint='')
        self._sync_collection_selection()
        self.update(ready=True, title=video.title,
                    thumbnail=self.images.add(video.thumbnail_bytes) if video.thumbnail_bytes else '',
                    formats=labels, formatIndex=selected, filename=sanitize_filename(video.title),
                    directory=self._default_directory)
        self._set_text('meta', 'download.meta_collection' if is_playlist else 'download.meta_single',
                       {'channel': video.channel, 'count': len(video.entries)} if is_playlist
                       else {'channel': video.channel, 'duration': format_duration(video.duration)})
        if profile is not None:
            self._subtitle_preferences.update(enabled=profile.subtitle_enabled, auto=profile.subtitle_auto,
                                              embed=profile.subtitle_embed)
            self.update(audioCodec=profile.audio_codec, audioQuality=profile.audio_quality,
                        subtitleFormat=profile.subtitle_format)
            self.selectMode(profile.content_mode)
            if profile.content_mode == 'audio_only':
                self.selectAudio(profile.audio_codec, profile.audio_quality)
            preferred_quality = profile.quality_tier
        else:
            self.selectMode('audio_only' if not video.formats and video.audio_formats else 'video_audio')
        options = self.available_formats
        if is_playlist:
            initial_target = (preferred_quality if self.video.collection_quality_mode == 'RESOLVED_COMMON_FORMATS'
                              else 'highest')
            self.update(collectionQuality=initial_target)
            self._refresh_collection_quality_targets()
        elif options:
            if preferred_quality == 'highest':
                selected = max(range(len(options)), key=lambda i: options[i].quality_sort_key)
            elif preferred_quality in {'2160p', '1440p', '1080p', '720p'}:
                selected = next((i for i, option in enumerate(options)
                                 if option.display_height == int(preferred_quality[:-1])), 0)
            elif preferred_quality == 'recommended':
                selected = next((i for i, option in enumerate(options) if option.is_recommended), 0)
            else:
                selected = next((i for i, option in enumerate(options) if option.label == preferred_quality), 0)
            self.selectFormat(selected)
        self.update(qualityAuto=preferred_quality == 'recommended' and self._state['mediaMode'] == 'video_audio')
        self._subtitle_state(reset_selection=True)
        if profile is not None and profile.subtitle_languages and self._state['subtitleEnabled']:
            available = {item['code'] for item in self._state['subtitleChoices']}
            languages = [code for code in profile.subtitle_languages if code in available]
            if languages:
                self.update(subtitleLanguages=languages)
                self._subtitle_state()
        self._validate_clip_state()

    def _collection_entry_detail(self, entry):
        details = []
        if entry.duration is not None:
            details.append(format_duration(entry.duration))
        options = self._entry_options(entry) if entry.embedded else ()
        if options:
            best = max(options, key=lambda option: option.quality_sort_key)
            details.append(self._t('collection.entry_quality', {'quality': best.label}))
        elif not entry.unavailable:
            details.append(self._t('collection.entry_pending'))
        return ' · '.join(details) or (self._t('collection.entry_unavailable') if entry.unavailable else self._t('collection.entry_item'))

    @property
    def available_formats(self):
        if not self.video:
            return ()
        mode = self._state['mediaMode']
        if mode == 'audio_only':
            choices = self.video.audio_formats
            codec = self._state['audioCodec']
            matching = tuple(option for option in choices if
                             (codec == 'm4a' and option.acodec.startswith(('mp4a', 'aac'))) or
                             (codec == 'opus' and option.acodec == 'opus'))
            return matching or choices
        if mode == 'video_only':
            choices = self.video.video_only_formats
        else:
            choices = self.video.formats
        if self._format_codec_preference is CodecPreference.AUTO:
            return choices
        return tuple(apply_codec_preference(option, self._format_codec_preference) for option in choices)

    @Slot(str)
    def selectMode(self, mode):
        if mode not in {'video_audio', 'video_only', 'audio_only'}:
            return
        self.update(mediaMode=mode)
        options = self.available_formats
        hint = self._t('download.mode_video_hint') if mode == 'video_only' else self._t('download.mode_audio_hint') if mode == 'audio_only' else ''
        if not options and not self._state['playlist']:
            hint = self._t('download.mode_unavailable')
        self.update(formats=[option.label for option in options], formatIndex=0, technical='')
        self._set_text('modeHint', 'download.mode_video_hint' if mode == 'video_only' else 'download.mode_audio_hint' if mode == 'audio_only' else None)
        if not options and not self._state['playlist']:
            self._set_text('modeHint', 'download.mode_unavailable')
        self.selectFormat(0)
        self.update(qualityAuto=mode == 'video_audio')
        if self.video and self._state['collection']:
            for index, entry in enumerate(self.video.entries):
                row = self._entries.get(index)
                choices = self._entry_options(entry)
                if entry.embedded and not choices:
                    self._selected_entries.discard(index)
                self._entries.put(dict(row, unavailable=entry.unavailable or (entry.embedded and not choices),
                                       selected=index in self._selected_entries))
            self.update(selectedCount=len(self._selected_entries))
            self._sync_collection_selection()
            self._refresh_collection_quality_targets()
        self._subtitle_state()

    @Slot(bool)
    def setQualityAuto(self, enabled):
        if self._state['mediaMode'] != 'video_audio':
            return
        self.update(qualityAuto=bool(enabled))

    def _subtitle_state(self, *, reset_selection=False):
        """Project subtitle preferences onto the current media's real capability."""
        from yt_downloader.services.subtitle_service import language_name
        manual_tracks = self.video.subtitles if self.video else ()
        auto_tracks = self.video.automatic_captions if self.video else ()
        has_manual, has_auto = bool(manual_tracks), bool(auto_tracks)
        capability = ('MANUAL_AND_AUTO' if has_manual and has_auto else 'MANUAL_ONLY' if has_manual
                      else 'AUTO_ONLY' if has_auto else 'NONE')
        can_download = capability != 'NONE' and not self._state['playlist']
        enabled = bool(self._subtitle_preferences['enabled'] and can_download)
        auto = bool(enabled and has_auto and (not has_manual or self._subtitle_preferences['auto']))
        tracks = (*manual_tracks, *(auto_tracks if auto else ()))
        available_codes = tuple(dict.fromkeys(track.language for track in tracks))
        selected = [] if reset_selection else [code for code in self._state['subtitleLanguages'] if code in available_codes]
        if enabled and not selected:
            selected = list(available_codes)
        enabled = bool(enabled and selected)
        if not enabled:
            auto = False
            selected = []
            available_codes = ()
        choices = [dict(code=code, name=language_name(code), selected=code in selected) for code in available_codes]
        options = self.available_formats
        index = self._state['formatIndex']
        can_embed = bool(enabled and self.subtitle_ffmpeg_available and self._state['mediaMode'] != 'audio_only'
                         and ((0 <= index < len(options) and options[index].final_ext in {'mp4', 'mkv'}) or self._state['playlist']))
        embed = bool(self._subtitle_preferences['embed'] and can_embed)
        manual_status_key = 'download.subtitle_manual_status' if manual_tracks else 'download.subtitle_manual_none'
        auto_status_key = 'download.subtitle_auto_status' if auto_tracks else 'download.subtitle_auto_none'
        if capability == 'NONE':
            embed_hint_key = 'download.no_subtitles'
        elif not enabled:
            embed_hint_key = 'download.subtitle_embed_select'
        elif self._state['mediaMode'] == 'audio_only':
            embed_hint_key = 'download.subtitle_embed_audio'
        elif not self.subtitle_ffmpeg_available:
            embed_hint_key = 'download.subtitle_embed_ffmpeg'
        elif not options or not (0 <= index < len(options)) or options[index].final_ext not in {'mp4', 'mkv'}:
            embed_hint_key = 'download.subtitle_embed_container'
        else:
            embed_hint_key = ''
        self.update(subtitleEnabled=enabled, subtitleAuto=auto, subtitleEmbed=embed,
                    subtitleLanguages=selected, subtitleChoices=choices, subtitleCapability=capability,
                    subtitleCanDownload=can_download, subtitleCanAuto=bool(enabled and has_manual and has_auto),
                    subtitleCanFormat=enabled, subtitleCanEmbed=can_embed)
        self._set_text('subtitleManualStatus', manual_status_key, {'count': len(manual_tracks)} if manual_tracks else None)
        self._set_text('subtitleAutoStatus', auto_status_key, {'count': len(auto_tracks)} if auto_tracks else None)
        self._set_text('subtitleEmbedHint', embed_hint_key)
        self._set_text('subtitleHint', 'download.no_subtitles' if capability == 'NONE' else None)
        self._set_text('subtitleAutoHint', 'download.auto_captions_missing' if has_manual and not has_auto else None)

    @Slot(str, bool)
    def setSubtitleOption(self, name, enabled):
        if name in self._subtitle_preferences:
            self._subtitle_preferences[name] = enabled
            self._subtitle_state()

    @Slot(str, bool)
    def selectSubtitle(self, code, enabled):
        if not self._state['subtitleEnabled'] or code not in {item['code'] for item in self._state['subtitleChoices']}:
            return
        codes = list(self._state['subtitleLanguages'])
        if enabled and code not in codes:
            codes.append(code)
        if not enabled and code in codes:
            codes.remove(code)
        if not codes:
            self._subtitle_preferences['enabled'] = False
            self._subtitle_preferences['embed'] = False
        self.update(subtitleLanguages=codes)
        self._subtitle_state()

    @Slot(str)
    def selectSubtitleFormat(self, value):
        if self._state['subtitleCanFormat'] and value in {'srt', 'vtt'}:
            self.update(subtitleFormat=value)

    @Slot(str, str)
    def selectAudio(self, codec, quality):
        if codec not in {'original', 'm4a', 'mp3', 'opus', 'flac'} or quality not in {'original', '320', '256', '192', '128'}:
            return
        self.update(audioCodec=codec, audioQuality=quality)
        self.selectMode(self._state['mediaMode'])

    def set_thumbnail(self, media_key, thumbnail_bytes):
        if self.video is None or self.video.media_key != media_key:
            return False
        source = self.images.add(thumbnail_bytes)
        if not source:
            return False
        self.video = replace(self.video, thumbnail_bytes=thumbnail_bytes)
        self.update(thumbnail=source)
        return True

    @Slot(int)
    def selectFormat(self, index):
        if self.video is None or not 0 <= index < len(self.available_formats):
            return
        option = self.available_formats[index]
        size = format_bytes(option.estimated_size) if option.estimated_size is not None else ''
        self._format_option = option
        self._format_summary = self._technical_summary(option)
        self._format_size_key = ('download.size_unknown' if option.estimated_size is None else
                                 'download.size_estimated' if option.size_is_estimate else 'download.size')
        self._format_size_params = {'size': size} if size else {}
        self.update(formatIndex=index, qualityAuto=False,
                    technical=f'{self._format_summary}  ·  {self._t(self._format_size_key, self._format_size_params)}')
        self._subtitle_state()

    def _technical_summary(self, option):
        if option.vcodec == 'none':
            return f'{option.container} · {option.acodec.upper()} · {self._t("format.audio_only")}'
        codec = option.vcodec.split('.', 1)[0].upper()
        audio = (option.acodec.split('.', 1)[0].upper()
                 if option.acodec != 'none' else self._t('format.no_audio'))
        merge = f' · {self._t("download.requires_merge")}' if option.requires_merge else ''
        return f'{option.container} · {codec} · {audio}{merge}'

    def set_default_directory(self, directory):
        self._default_directory = directory
        if self.video is None or not self._directory_overridden:
            self.update(directory=directory)

    def set_retry_defaults(self, filename, directory):
        self._directory_overridden = True
        self.update(filename=filename, directory=directory)

    @Slot()
    def requestDownload(self):
        index = self._state['formatIndex']
        if self.video and self._state['playlist'] and self._selected_entries and not self._state['busy']:
            selected = []
            target = self._state['collectionQuality']
            for row_index in sorted(self._selected_entries):
                entry = self.video.entries[row_index]
                selected.append(replace(entry, selected_format=None, quality_target=target))
            self.collection_download_requested.emit(self.video, tuple(selected))
            return
        if self.video and 0 <= index < len(self.available_formats) and not self._state['busy']:
            self._validate_clip_state()
            if not self._state['clipValid']:
                return
            self.download_requested.emit(self.video, self.available_formats[index], self._state['filename'], self._state['directory'])

    def add_task(self, request):
        from yt_downloader.services.download_options import prepare_request
        effective = request if request.resolve_before_download else prepare_request(request)
        card = TaskPresentation(request)
        card.values = dict(id=request.task_id, title=request.video.title,
                           quality=f'{effective.format.label} · {effective.format.container}',
                           clipRange=(f'{format_duration(request.clip_start)}–{format_duration(request.clip_end)}'
                                      if request.clip_enabled else ''),
                           thumbnail=self._thumbnail_source(request.video.thumbnail_bytes,
                                                            request.video.thumbnail_url),
                           warningMessages=[],
                           cancel=True, cancelEnabled=True, cancelText='取消', open=False, folder=False)
        card.progress(DownloadProgress(request.task_id, TaskStatus.PENDING))
        self.cards[request.task_id] = card
        self._terminal_task_ids.discard(request.task_id)
        self._tasks.put(dict(card.values))

    def update_task(self, progress):
        card = self.cards.get(progress.task_id)
        if card:
            thumbnail = self._thumbnail_source(progress.resolved_thumbnail_bytes,
                                               progress.resolved_thumbnail_url,
                                               card.values.get('thumbnail', ''))
            if thumbnail:
                card.values['thumbnail'] = thumbnail
            card.progress(progress)
            self._tasks.put(dict(card.values))

    def _thumbnail_source(self, thumbnail_bytes, thumbnail_url, fallback=''):
        if thumbnail_bytes:
            source = self.images.add(thumbnail_bytes)
            if source:
                return source
        return thumbnail_url or fallback or ''

    def cancel_task(self, task_id):
        card = self.cards.get(task_id)
        if card:
            card.progress(DownloadProgress(task_id, TaskStatus.CANCELLING))
            card.values.update(cancelEnabled=False, cancelText='正在取消…')
            self._tasks.put(dict(card.values))

    def pausing_task(self, task_id):
        self.update_task(DownloadProgress(task_id, TaskStatus.PAUSING))

    def paused_task(self, task_id):
        self.update_task(DownloadProgress(task_id, TaskStatus.PAUSED))

    def resuming_task(self, task_id):
        self.update_task(DownloadProgress(task_id, TaskStatus.RESUMING))

    def complete_task(self, result):
        card = self.cards.get(result.task_id)
        if card:
            card.file_path = result.file_path
            card.progress(DownloadProgress(result.task_id, TaskStatus.COMPLETED, 100, result.file_size, result.file_size))
            card.values.update(cancel=False, open=True, folder=True)
            if result.resolved_media and result.resolved_format:
                card.values.update(title=result.resolved_media.title, quality=f'{result.resolved_format.label} · {result.resolved_format.container}')
            if result.resolved_media:
                card.values['thumbnail'] = self._thumbnail_source(
                    result.resolved_media.thumbnail_bytes, result.resolved_media.thumbnail_url,
                    card.values.get('thumbnail', ''))
            if result.warnings:
                card.values['warningMessages'] = list(result.warnings)
            self._tasks.put(dict(card.values))
            self._mark_terminal(result.task_id)

    def fail_task(self, task_id, status, cleanup_report: CancellationCleanupReport | None = None):
        card = self.cards.get(task_id)
        if card:
            card.progress(DownloadProgress(task_id, status))
            card.values['cancel'] = False
            if status is TaskStatus.CANCELLED and cleanup_report is not None and not cleanup_report.succeeded:
                card.values.update(warningMessages=['任务由用户取消，但部分临时文件未能清理；可打开下载文件夹处理。'], folder=True)
                card.file_path = Path(cleanup_report.output_directory)
            self._tasks.put(dict(card.values))
            self._mark_terminal(task_id)

    def _mark_terminal(self, task_id):
        for previous in tuple(self._terminal_task_ids):
            if previous != task_id:
                self.remove_task(previous)
        self._terminal_task_ids.add(task_id)

    def task_started(self, task_id):
        self.update_task(DownloadProgress(task_id, TaskStatus.FETCHING_METADATA))
        for previous in tuple(self._terminal_task_ids):
            if previous != task_id:
                self.remove_task(previous)

    def remove_task(self, task_id):
        card = self.cards.get(task_id)
        self._terminal_task_ids.discard(task_id)
        self.cards.pop(task_id, None)
        self._tasks.remove(task_id)

    def task_status(self, task_id):
        return self.cards[task_id].status if task_id in self.cards else None

    def task_request(self, task_id):
        return self.cards[task_id].request if task_id in self.cards else None

    @Slot(str, str)
    def taskAction(self, task_id, action):
        card = self.cards.get(task_id)
        if card is None:
            return
        if action == 'remove':
            self.remove_requested.emit(task_id)
        elif action == 'pause' and card.values['pauseEnabled']:
            self.pause_requested.emit(task_id)
        elif action == 'resume' and card.values['resumeEnabled']:
            self.resume_requested.emit(task_id)
        elif action == 'cancel' and card.values['cancel'] and card.values['cancelEnabled']:
            self.cancel_requested.emit(task_id)
        elif action == 'retry' and card.values['retry'] and not self._state['busy']:
            self.retry_requested.emit(task_id)
        elif action == 'open' and card.values['open']:
            self.open_file_requested.emit(str(card.file_path or ''))
        elif action == 'folder' and card.values['folder']:
            self.open_folder_requested.emit(str(card.file_path or ''))

"""Download presentation. Domain objects and command parameters stay in Python."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from yt_downloader.core.errors import CancellationCleanupReport
from yt_downloader.core.filename import sanitize_filename
from yt_downloader.core.formatting import format_bytes, format_duration, format_eta, format_speed
from yt_downloader.core.models import DownloadProgress, DownloadRequest, DownloadResult, ParseState, STATUS_TEXT, TaskStatus, VideoInfo
from yt_downloader.core.url import InvalidMediaUrl, normalize_media_url
from yt_downloader.ui.quick_state import RowModel, ViewState


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
        values.update(status=progress.status.value, statusText=STATUS_TEXT[progress.status],
                      indeterminate=not stopping and not held and progress.percent is None,
                      speed='—' if stopping or held else format_speed(progress.speed),
                      eta='剩余 —' if stopping or held else f'剩余 {format_eta(progress.eta)}',
                      retry=progress.status is TaskStatus.FAILED,
                      stopping=stopping or held,
                      pauseVisible=downloading or held or progress.status in {TaskStatus.MERGING, TaskStatus.POST_PROCESSING},
                      pauseEnabled=downloading, resumeEnabled=progress.status is TaskStatus.PAUSED,
                      pauseText='继续' if progress.status is TaskStatus.PAUSED else '正在暂停…' if progress.status is TaskStatus.PAUSING else '正在继续…' if progress.status is TaskStatus.RESUMING else '暂停')
        if not stopping and not held and progress.percent is not None:
            self.last_percent = round(progress.percent)
        values['percent'] = self.last_percent or 0
        values['percentText'] = f'{self.last_percent}%' if self.last_percent is not None and (stopping or held or progress.percent is not None) else '—%'
        if (not stopping and not held) or progress.downloaded_bytes is not None or progress.total_bytes is not None:
            total = format_bytes(progress.total_bytes)
            if progress.total_is_estimate and progress.total_bytes is not None:
                total = f'估算 {total}'
            values['size'] = f'{format_bytes(progress.downloaded_bytes)} / {total}'
        self.values = values


class DownloadPresenter(ViewState):
    batch_requested = Signal(object, object)
    batch_action_requested = Signal(str, str)
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

    def __init__(self, directory: str, images, parent=None):
        super().__init__(parent, url='', filename='', directory=directory, ready=False,
                         busy=False, cancelling=False, parseText='解析', parseHint='',
                         clipboardHint='', title='', meta='', thumbnail='', formats=[],
                         formatIndex=0, qualityAuto=True, technical='', compatibilityHint='', mediaHint='',
                         mediaMode='video_audio', audioCodec='original', audioQuality='original',
                         modeHint='', subtitleEnabled=False, subtitleAuto=False,
                         subtitleEmbed=False, subtitleFormat='srt', subtitleLanguages=[],
                         subtitleChoices=[], subtitleCapability='NONE', subtitleCanDownload=False,
                         subtitleCanAuto=False, subtitleCanFormat=False, subtitleCanEmbed=False,
                         subtitleHint='', subtitleAutoHint='', subtitleManualStatus='人工字幕：暂无',
                         subtitleAutoStatus='自动字幕：暂无', subtitleEmbedHint='',
                         playlist=False, selectedCount=0, playlistCount=0,
                         cookieEnabled=False, cookieHint='')
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
        self._batches = RowModel(self)
        self._batch_tasks = {}
        self._batch_paused = set()
        self._batch_expanded = set()
        self._entries = RowModel(self)
        self._selected_entries = set()
        self._cookie_profiles = ()
        self._active_cookie_profile = None
        self._subtitle_preferences = {'enabled': False, 'auto': False, 'embed': False}

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
        if not self._state['cookieEnabled'] or not self._state['url'].strip():
            hint = ''
        else:
            route = self._cookie_route()
            hint = ('此网站有多份同等匹配的 Cookie 配置，请在设置中整理后重试。' if route.status == 'conflict'
                    else '此网站未保存 Cookie 配置；可先匿名解析，或在设置中添加。' if route.status == 'missing' else '')
        self.update(cookieHint=hint)

    def _invalidate_media(self):
        self.video = None
        self._active_cookie_profile = None
        self.update(ready=False, title='', formats=[])
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
        if entry.unavailable:
            return
        if selected:
            self._selected_entries.add(index)
        else:
            self._selected_entries.discard(index)
        row = self._entries.get(index)
        self._entries.put(dict(row, selected=selected))
        self.update(selectedCount=len(self._selected_entries))

    @Slot(bool)
    def selectAllEntries(self, selected):
        if self.video:
            for index in range(len(self.video.entries)):
                self.selectEntry(index, selected)

    @Property(QObject, constant=True)
    def batches(self):
        return self._batches

    def add_batch(self, batch_id, media, selected_count, created_at):
        from yt_downloader.core.models import BatchTask
        self._batch_tasks[batch_id] = BatchTask(batch_id, media.url, media.title, len(media.entries) or selected_count,
                                                selected_count, created_at)
        self._refresh_batches()

    def finish_batch_registration(self, batch_id):
        batch = self._batch_tasks[batch_id]
        registered = sum(card.request.batch_id == batch_id for card in self.cards.values())
        if not registered:
            self._batch_tasks.pop(batch_id)
            self._batches.remove(batch_id)
        else:
            self._batch_tasks[batch_id] = replace(batch, selected_count=registered)
            self._refresh_batches()

    def _refresh_batches(self):
        for batch_id, batch in self._batch_tasks.items():
            states = [card.status for card in self.cards.values() if card.request.batch_id == batch_id]
            completed = states.count(TaskStatus.COMPLETED)
            failed = states.count(TaskStatus.FAILED)
            cancelled = states.count(TaskStatus.CANCELLED)
            queued = states.count(TaskStatus.PENDING) + max(0, batch.selected_count - len(states))
            active = len(states) - completed - failed - cancelled - states.count(TaskStatus.PENDING)
            status = 'paused' if batch_id in self._batch_paused else 'running' if active else 'queued'
            if completed + failed + cancelled == batch.selected_count:
                status = 'completed_with_errors' if failed else 'cancelled' if cancelled else 'completed'
            value = replace(batch, completed_count=completed, failed_count=failed, cancelled_count=cancelled,
                            queued_count=queued, active_count=active, status=status)
            self._batches.put(dict(asdict(value), id=batch_id, expanded=batch_id in self._batch_expanded,
                                   percent=int(100 * (completed + failed + cancelled) / max(1, batch.selected_count))))

    def failed_batch_requests(self, batch_id):
        return tuple(card.request for card in self.cards.values()
                     if card.request.batch_id == batch_id and card.status is TaskStatus.FAILED)

    @Slot(str, str)
    def batchAction(self, batch_id, action):
        if batch_id not in self._batch_tasks:
            return
        if action == 'expand':
            self._batch_expanded.symmetric_difference_update({batch_id})
            for card in self.cards.values():
                if card.request.batch_id == batch_id:
                    card.values['shown'] = batch_id in self._batch_expanded
                    self._tasks.put(dict(card.values))
        elif action == 'pause':
            self._batch_paused.add(batch_id)
        elif action == 'resume':
            self._batch_paused.discard(batch_id)
        self._refresh_batches()
        if action != 'expand':
            self.batch_action_requested.emit(batch_id, action)

    def set_clipboard_hint(self, text):
        try:
            normalized = normalize_media_url(text)
        except InvalidMediaUrl:
            self.update(clipboardHint='')
            return
        self.update(clipboardHint=f'剪贴板中有可用链接：{normalized}')

    @Slot(str, str)
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
        self.update(busy=busy, cancelling=cancelling,
                    parseText='正在取消…' if cancelling else '取消解析' if busy else '解析',
                    parseHint='连接较慢，仍在尝试。你可以取消解析。' if state is ParseState.SLOW else '')

    def show_video(self, video, *, preferred_quality='recommended'):
        self.video = video
        self._selected_entries.clear()
        self._entries.replace([dict(id=str(index), index=index, title=entry.title,
                                   url=entry.url, thumbnail=entry.thumbnail, unavailable=entry.unavailable,
                                   selected=False) for index, entry in enumerate(video.entries)])
        self.update(playlist=video.media_type == 'playlist', selectedCount=0, playlistCount=len(video.entries))
        self._directory_overridden = False
        selected = 0
        labels = []
        for index, option in enumerate(video.formats):
            labels.append(f'{option.label}（推荐）' if option.is_recommended else option.label)
            if (preferred_quality == 'recommended' and option.is_recommended) or option.label == preferred_quality:
                selected = index
        if video.metadata_compatibility == 'VERIFIED' and video.download_compatibility == 'EXPERIMENTAL':
            compatibility_hint = '该网站的媒体解析已验证，但下载兼容性仍属实验性；不会绕过登录、地区或 DRM 限制。'
        elif video.download_compatibility == 'EXPERIMENTAL':
            compatibility_hint = '该网站由 yt-dlp 支持，但尚未经过 YTDownloader 完整验证。'
        else:
            compatibility_hint = ''
        self.update(compatibilityHint=compatibility_hint,
                    mediaHint=('仅显示前 1000 项，请明确选择需要的项目。' if video.entries_truncated else '请选择需要的项目；不会自动下载整个列表或频道。') if video.media_type == 'playlist' else '', technical='')
        self.update(ready=True, title=video.title, meta=f'{video.channel}  ·  {format_duration(video.duration)}',
                    thumbnail=self.images.add(video.thumbnail_bytes) if video.thumbnail_bytes else '',
                    formats=labels, formatIndex=selected, filename=sanitize_filename(video.title),
                    directory=self._default_directory)
        self.selectFormat(selected)
        self.selectMode('audio_only' if not video.formats and video.audio_formats else 'video_audio')
        if self._state['mediaMode'] == 'video_audio':
            self.selectFormat(selected)
        self.update(qualityAuto=preferred_quality == 'recommended' and self._state['mediaMode'] == 'video_audio')
        self._subtitle_state(reset_selection=True)

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
            return self.video.video_only_formats
        return self.video.formats

    @Slot(str)
    def selectMode(self, mode):
        if mode not in {'video_audio', 'video_only', 'audio_only'}:
            return
        self.update(mediaMode=mode)
        options = self.available_formats
        hint = '仅视频：文件不会包含声音' if mode == 'video_only' else '目标码率不会提升源音频质量。' if mode == 'audio_only' else ''
        if not options and not self._state['playlist']:
            hint = '此媒体没有该模式可用的独立流，请选择其他下载模式。'
        self.update(formats=[option.label for option in options], formatIndex=0, modeHint=hint, technical='')
        self.selectFormat(0)
        self.update(qualityAuto=mode == 'video_audio')
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
        manual_status = f'人工字幕：可用（{len(manual_tracks)} 种）' if manual_tracks else '人工字幕：暂无'
        auto_status = f'自动字幕：可用（{len(auto_tracks)} 种）' if auto_tracks else '自动字幕：暂无'
        if capability == 'NONE':
            embed_hint = '没有可用字幕。'
        elif not enabled:
            embed_hint = '请先选择要下载的字幕。'
        elif self._state['mediaMode'] == 'audio_only':
            embed_hint = '仅音频模式不支持嵌入字幕。'
        elif not self.subtitle_ffmpeg_available:
            embed_hint = '未找到 FFmpeg，无法嵌入字幕。'
        elif not options or not (0 <= index < len(options)) or options[index].final_ext not in {'mp4', 'mkv'}:
            embed_hint = '当前容器不支持字幕嵌入，请选择独立字幕文件。'
        else:
            embed_hint = ''
        hint = '该视频没有可用字幕。' if capability == 'NONE' else ''
        auto_hint = '该视频没有自动生成字幕。' if has_manual and not has_auto else ''
        self.update(subtitleEnabled=enabled, subtitleAuto=auto, subtitleEmbed=embed,
                    subtitleLanguages=selected, subtitleChoices=choices, subtitleCapability=capability,
                    subtitleCanDownload=can_download, subtitleCanAuto=bool(enabled and has_manual and has_auto),
                    subtitleCanFormat=enabled, subtitleCanEmbed=can_embed, subtitleHint=hint,
                    subtitleAutoHint=auto_hint, subtitleManualStatus=manual_status,
                    subtitleAutoStatus=auto_status, subtitleEmbedHint=embed_hint)

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
        size = format_bytes(option.estimated_size)
        size_text = '大小未知' if option.estimated_size is None else f'估算 {size}' if option.size_is_estimate else f'大小 {size}'
        self.update(formatIndex=index, qualityAuto=False, technical=f'{option.technical_summary}  ·  {size_text}')
        self._subtitle_state()

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
            self.batch_requested.emit(self.video, tuple(self.video.entries[i] for i in sorted(self._selected_entries)))
            return
        if self.video and 0 <= index < len(self.available_formats) and not self._state['busy']:
            self.download_requested.emit(self.video, self.available_formats[index], self._state['filename'], self._state['directory'])

    def add_task(self, request):
        from yt_downloader.services.download_options import prepare_request
        effective = request if request.resolve_before_download else prepare_request(request)
        card = TaskPresentation(request)
        card.values = dict(id=request.task_id, title=request.video.title,
                           batchId=request.batch_id, shown=not request.batch_id or request.batch_id in self._batch_expanded,
                           quality=f'{effective.format.label} · {effective.format.container}',
                           thumbnail=self.images.add(request.video.thumbnail_bytes) if request.video.thumbnail_bytes else '',
                           cancel=True, cancelEnabled=True, cancelText='取消', open=False, folder=False)
        card.progress(DownloadProgress(request.task_id, TaskStatus.PENDING))
        self.cards[request.task_id] = card
        self._terminal_task_ids.discard(request.task_id)
        self._tasks.put(dict(card.values))
        self._refresh_batches()

    def update_task(self, progress):
        card = self.cards.get(progress.task_id)
        if card:
            card.progress(progress)
            self._tasks.put(dict(card.values))
            self._refresh_batches()

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
            if result.warnings:
                card.values['statusText'] = '下载完成 · ' + '；'.join(result.warnings)
            self._tasks.put(dict(card.values))
            self._mark_terminal(result.task_id)

    def fail_task(self, task_id, status, cleanup_report: CancellationCleanupReport | None = None):
        card = self.cards.get(task_id)
        if card:
            card.progress(DownloadProgress(task_id, status))
            card.values['cancel'] = False
            if status is TaskStatus.CANCELLED and cleanup_report is not None and not cleanup_report.succeeded:
                card.values.update(statusText='已取消，但部分临时文件未能清理', folder=True)
                card.file_path = Path(cleanup_report.output_directory)
            self._tasks.put(dict(card.values))
            self._mark_terminal(task_id)

    def _mark_terminal(self, task_id):
        for previous in tuple(self._terminal_task_ids):
            if previous != task_id and not self.cards[previous].request.batch_id:
                self.remove_task(previous)
        self._terminal_task_ids.add(task_id)
        self._refresh_batches()

    def task_started(self, task_id):
        self.update_task(DownloadProgress(task_id, TaskStatus.FETCHING_METADATA))
        for previous in tuple(self._terminal_task_ids):
            if previous != task_id and not self.cards[previous].request.batch_id:
                self.remove_task(previous)

    def remove_task(self, task_id):
        card = self.cards.get(task_id)
        if card and card.request.batch_id:
            card.values['shown'] = False
            self._tasks.put(dict(card.values))
            return
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

"""Media tools reuse Download's URL, Cookie and parse presentation contract."""
from pathlib import Path
from PySide6.QtCore import Signal, Slot, Property, QObject
from yt_downloader.ui.quick_download import DownloadPresenter
from yt_downloader.services.subtitle_service import language_name
from yt_downloader.services.toolbox_service import ToolRequest
from yt_downloader.ui.quick_state import RowModel


class ToolboxPresenter(DownloadPresenter):
    tool_requested = Signal(object)
    tool_cancel_requested = Signal()
    preview_requested = Signal(str)

    def __init__(self, directory, images, parent=None, translator=None):
        super().__init__(directory, images, parent, translator)
        self.update(category=0, toolBusy=False, thumbnailChoices=[], thumbnailIndex=0,
                    toolSubtitleChoices=[], toolSubtitleLanguages=[], includeAuto=False,
                    toolSubtitleFormat='srt', resultFiles=[], toolStatus='', toolWarningCount=0)
        self._tool_status_key = ''
        self._tool_status_params = {}
        self._preview_url = ''
        self._preview_cache = {}
        self._subtitle_rows = RowModel(self)

    @Property(QObject, constant=True)
    def subtitleEntries(self):
        return self._subtitle_rows

    @Slot(int)
    def selectCategory(self, index):
        if index in {0, 1, 2}:
            self.update(category=index)

    def show_video(self, video, **_kwargs):
        super().show_video(video)
        self.update(thumbnailIndex=0, toolSubtitleLanguages=[], resultFiles=[])
        self._tool_status_key = ''
        self.update(toolStatus='')
        self._preview_url = ''
        self._refresh_tools()

    def _refresh_tools(self):
        candidates = sorted(self.video.thumbnails if self.video else (),
            key=lambda item: ((item.width or 0) * (item.height or 0), item.preference), reverse=True)
        choices = []
        for index, item in enumerate(candidates):
            label = self._t('toolbox.best_thumbnail') if index == 0 else self._t('toolbox.thumbnail_number', {'number': index + 1})
            if item.width and item.height:
                label += f' · {item.width} × {item.height}'
            choices.append(dict(label=label, url=item.url))
        self.update(thumbnailChoices=choices)
        if choices:
            index = min(self._state['thumbnailIndex'], len(choices) - 1)
            self.update(thumbnailIndex=index)
            self._select_preview(choices[index]['url'])
        manual = {track.language for track in self.video.subtitles if self._supported(track)} if self.video else set()
        auto = ({track.language for track in self.video.automatic_captions if self._supported(track)} - manual
                if self.video and self._state['includeAuto'] else set())
        codes = sorted(manual) + sorted(auto)
        selected = [code for code in self._state['toolSubtitleLanguages'] if code in codes]
        self.update(toolSubtitleLanguages=selected,
                    toolSubtitleChoices=[dict(code=code, name=language_name(code), auto=code in auto,
                                              selected=code in selected) for code in codes])
        self._subtitle_rows.replace([dict(id=row['code'], **row) for row in self._state['toolSubtitleChoices']])
        if self._tool_status_key:
            self.update(toolStatus=self._t(self._tool_status_key, self._tool_status_params))

    @staticmethod
    def _supported(track):
        return track.extension in {'srt', 'vtt', 'ttml', 'dfxp', 'ass', 'ssa'}

    @Slot(str)
    def _refresh_localized(self, locale=None):
        super()._refresh_localized(locale)
        if 'thumbnailChoices' in self._state:
            self._refresh_tools()

    @Slot(int)
    def selectThumbnail(self, index):
        if not self._state['toolBusy'] and 0 <= index < len(self._state['thumbnailChoices']):
            self.update(thumbnailIndex=index)
            self._select_preview(self._state['thumbnailChoices'][index]['url'])

    def _select_preview(self, url):
        changed = url != self._preview_url
        self._preview_url = url
        self.update(thumbnail=self._preview_cache.get(url, ''))
        if changed and url not in self._preview_cache:
            self.preview_requested.emit(url)

    def set_tool_preview(self, url, data):
        source = self.images.add(data)
        if source:
            self._preview_cache[url] = source
            if len(self._preview_cache) > 32:
                self._preview_cache.pop(next(iter(self._preview_cache)))
            if url == self._preview_url:
                self.update(thumbnail=source)

    @Slot(bool)
    def setIncludeAuto(self, enabled):
        self.update(includeAuto=bool(enabled))
        self._refresh_tools()

    @Slot(str, bool)
    def selectToolSubtitle(self, code, selected):
        valid = {row['code'] for row in self._state['toolSubtitleChoices']}
        if code not in valid:
            return
        languages = set(self._state['toolSubtitleLanguages'])
        languages.add(code) if selected else languages.discard(code)
        self.update(toolSubtitleLanguages=sorted(languages))
        self._refresh_tools()

    @Slot(str)
    def setToolSubtitleFormat(self, value):
        if value in {'srt', 'vtt', 'ass'}:
            self.update(toolSubtitleFormat=value)

    @Slot()
    def requestTool(self):
        if self._state['category'] == 2:
            return
        if self._state['toolBusy']:
            self.tool_cancel_requested.emit()
            return
        if not self.video or self._state['busy'] or not self._state['directory'].strip():
            return
        category = self._state['category']
        choices = self._state['thumbnailChoices']
        if category == 0 and not choices or category == 1 and not self._state['toolSubtitleLanguages']:
            return
        request = ToolRequest('thumbnail' if category == 0 else 'subtitles', self.video,
            Path(self._state['directory']),
            thumbnail_url=choices[self._state['thumbnailIndex']]['url'] if category == 0 else '',
            subtitle_languages=tuple(self._state['toolSubtitleLanguages']),
            subtitle_auto=self._state['includeAuto'], subtitle_format=self._state['toolSubtitleFormat'],
            cookie_profile=self._active_cookie_profile if self._state['cookieEnabled'] else None)
        self.tool_requested.emit(request)

    def tool_completed(self, result):
        self._tool_status_key = 'toolbox.saved_partial' if result.warning_count else 'toolbox.saved'
        self._tool_status_params = {'count': len(result.files), 'failed': result.warning_count}
        self.update(toolBusy=False, resultFiles=[str(path) for path in result.files])
        self._refresh_tools()

    @Slot(int)
    def openResult(self, index):
        if 0 <= index < len(self._state['resultFiles']):
            self.open_file_requested.emit(self._state['resultFiles'][index])

    @Slot()
    def openResultFolder(self):
        if self._state['resultFiles']:
            self.open_folder_requested.emit(self._state['resultFiles'][0])

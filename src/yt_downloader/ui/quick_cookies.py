"""Cookie references and explicit user selection; no credential values in UI state."""
from datetime import datetime, timezone
from pathlib import Path
import uuid

from PySide6.QtCore import Signal, Slot, QUrl
from yt_downloader.core.models import CookieProfile
from yt_downloader.services.cookie_service import cookie_options, recommended_profile
from yt_downloader.ui.quick_state import ViewState


class CookiePresenter(ViewState):
    save_requested = Signal(object)
    pick_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, profiles=['不使用'], profileIndex=0, source='none', browser='chrome',
                         name='', domain='', fileLabel='未选择文件', message='', authRequired=False, recommendation='')
        self.profiles = ()
        self._file_path = ''

    @property
    def selected_profile(self):
        index = self._state['profileIndex'] - 1
        return self.profiles[index] if 0 <= index < len(self.profiles) else None

    def set_profiles(self, profiles):
        selected = self.selected_profile
        self.profiles = tuple(profiles)
        index = next((i + 1 for i, profile in enumerate(self.profiles) if selected and profile.id == selected.id), 0)
        self.update(profiles=['不使用', *(profile.name for profile in self.profiles)], profileIndex=index)

    @Slot(int)
    def selectProfile(self, index):
        if not 0 <= index <= len(self.profiles):
            return
        self.update(profileIndex=index)
        profile = self.selected_profile
        self._file_path = profile.cookie_file if profile else ''
        self.update(source=profile.source_type if profile else 'none', name=profile.name if profile else '',
                    browser=profile.browser or 'chrome' if profile else 'chrome', domain=profile.domain_hint if profile else '',
                    fileLabel='…/' + Path(self._file_path).name if self._file_path else '未选择文件')

    @Slot(str, str)
    def edit(self, name, value):
        if name == 'source' and value == 'none':
            self.selectProfile(0)
            return
        if name in {'source', 'browser', 'name', 'domain'}:
            self.update(**{name: value})

    @Slot(str)
    def fileSelected(self, url):
        self._file_path = QUrl(url).toLocalFile()
        self.update(fileLabel='…/' + Path(self._file_path).name, source='file')

    @Slot()
    def saveProfile(self):
        if self._state['source'] == 'none':
            self.selectProfile(0)
            return
        now = datetime.now(timezone.utc).isoformat()
        old = self.selected_profile
        profile = CookieProfile(old.id if old else uuid.uuid4().hex,
                                self._state['name'].strip() or 'Cookie 配置', self._state['source'],
                                self._state['browser'], self._file_path, self._state['domain'].strip().lower(),
                                old.created_at if old else now, now)
        try:
            cookie_options(profile)
        except ValueError as error:
            self.update(message=str(error))
            return
        values = tuple(item for item in self.profiles if item.id != profile.id) + (profile,)
        self.save_requested.emit(values)

    @Slot()
    def removeProfile(self):
        profile = self.selected_profile
        if profile:
            self.save_requested.emit(tuple(item for item in self.profiles if item.id != profile.id))

    def recommend(self, url):
        profile = recommended_profile(self.profiles, url)
        self.update(recommendation=f'可选配置：{profile.name}（需自行选择）' if profile else '')

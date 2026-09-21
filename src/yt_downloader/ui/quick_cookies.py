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
    delete_requested = Signal(object)
    pick_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, profiles=['不使用'], profileIndex=0, source='none', browser='chrome',
                         name='', domain='', fileLabel='未选择文件', message='', authRequired=False, recommendation='',
                         modeOptions=[
                             {'id': 'none', 'label': '不使用', 'description': '适合绝大多数公开内容'},
                             {'id': 'browser', 'label': '从浏览器读取', 'description': '使用你已经登录的网站状态'},
                             {'id': 'file', 'label': '使用 cookies.txt', 'description': '使用本地 Netscape Cookie 文件'},
                         ], profileCards=[])
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
        cards = [self._profile_card(profile) for profile in self.profiles]
        self.update(profiles=['不使用', *(profile.name for profile in self.profiles)], profileCards=cards, profileIndex=index)

    @staticmethod
    def _profile_card(profile):
        if profile.source_type == 'browser':
            source = profile.browser or '浏览器'
            summary = source.capitalize()
        else:
            summary = 'cookies.txt'
        if profile.domain_hint:
            summary += f' · {profile.domain_hint}'
        return {'id': profile.id, 'name': profile.name, 'summary': summary,
                'source': profile.source_type, 'browser': profile.browser or '',
                'domain': profile.domain_hint or '', 'fileLabel': Path(profile.cookie_file).name if profile.cookie_file else ''}

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

    @Slot()
    def newProfile(self):
        self._file_path = ''
        self.selectProfile(0)
        self.update(source='browser', name='', domain='', browser='chrome', fileLabel='未选择文件', message='')

    @Slot(int)
    def editProfile(self, index):
        self.selectProfile(index + 1 if 0 <= index < len(self.profiles) else 0)

    @Slot()
    def testProfile(self):
        if self._state['source'] == 'file':
            try:
                cookie_options(CookieProfile('test', 'test', 'file', cookie_file=self._file_path))
            except ValueError as error:
                self.update(message=str(error))
                return
            self.update(message='Cookie 文件格式有效；保存后仅在解析时使用。')
        elif self._state['source'] == 'browser':
            self.update(message='将使用当前浏览器的登录状态；保存后在解析时读取。')

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
        source = self._state['source']
        default_name = f"{self._state['domain'].strip() or '网站'} - {(self._state['browser'] or '浏览器').capitalize()}" if source == 'browser' else 'cookies.txt 配置'
        profile = CookieProfile(old.id if old else uuid.uuid4().hex,
                                self._state['name'].strip() or default_name, source,
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
            self.delete_requested.emit(profile)

    def recommend(self, url):
        profile = recommended_profile(self.profiles, url)
        self.update(recommendation=f'可选配置：{profile.name}（需自行选择）' if profile else '')

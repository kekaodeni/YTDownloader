"""Cookie profile presentation and selection.

Only references to a browser or cookie file are kept here. The presenter is
the single source of truth shared by Settings and Download pages.
"""
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from PySide6.QtCore import Signal, Slot, QUrl

from yt_downloader.core.models import CookieProfile
from yt_downloader.services.cookie_service import cookie_options
from yt_downloader.ui.quick_state import ViewState


class CookiePresenter(ViewState):
    save_requested = Signal(object)
    delete_requested = Signal(object)
    pick_requested = Signal()
    editor_requested = Signal(object)
    profiles_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, profiles=['不使用'], profileIndex=0,
                         source='none', browser='chrome', browserProfile='', name='', domain='',
                         fileLabel='未选择文件', message='', authRequired=False,
                         modeOptions=[
                             {'id': 'none', 'label': '不使用', 'description': '适合绝大多数公开内容'},
                             {'id': 'browser', 'label': '从浏览器读取', 'description': '使用你已经登录的网站状态'},
                             {'id': 'file', 'label': '使用 cookies.txt', 'description': '使用本地 Netscape Cookie 文件'},
                         ], profileCards=[])
        self.profiles = ()
        self._file_path = ''
        self._editor_session = None
        self._save_failed = False

    @property
    def selected_profile(self):
        index = self._state['profileIndex'] - 1
        return self.profiles[index] if 0 <= index < len(self.profiles) else None

    def set_profiles(self, profiles):
        selected = self.selected_profile
        self.profiles = tuple(profiles)
        index = next((i + 1 for i, profile in enumerate(self.profiles)
                      if selected and profile.id == selected.id), 0)
        cards = [self._profile_card(profile) for profile in self.profiles]
        self.update(profiles=['不使用', *(profile.name for profile in self.profiles)],
                    profileCards=cards, profileIndex=index)
        self.profiles_changed.emit(self.profiles)

    @staticmethod
    def _profile_card(profile):
        if profile.source_type == 'browser':
            summary = (profile.browser or '浏览器').capitalize()
        else:
            summary = 'cookies.txt'
        if profile.domain_hint:
            summary += f' · {profile.domain_hint}'
        return {'id': profile.id, 'name': profile.name, 'summary': summary,
                'source': profile.source_type, 'browser': profile.browser or '',
                'browserProfile': profile.browser_profile or '',
                'domain': profile.domain_hint or '',
                'fileLabel': Path(profile.cookie_file).name if profile.cookie_file else ''}

    @Slot(int)
    def selectProfile(self, index):
        if not 0 <= index <= len(self.profiles):
            return
        self.update(profileIndex=index)
        profile = self.selected_profile
        self._file_path = profile.cookie_file if profile else ''
        self.update(source=profile.source_type if profile else 'none',
                    name=profile.name if profile else '',
                    browser=profile.browser or 'chrome' if profile else 'chrome',
                    browserProfile=profile.browser_profile if profile else '', domain=profile.domain_hint if profile else '',
                    fileLabel='…/' + Path(self._file_path).name if self._file_path else '未选择文件')

    @Slot(str, str)
    def edit(self, name, value):
        if name == 'source' and value == 'none':
            self.selectProfile(0)
            return
        if name in {'source', 'browser', 'browserProfile', 'name', 'domain'}:
            self.update(**{name: value})

    @Slot()
    def newProfile(self):
        self._file_path = ''
        self.selectProfile(0)
        self.update(source='browser', name='', domain='', browser='chrome', browserProfile='',
                    fileLabel='未选择文件', message='')
        self.editor_requested.emit(None)

    @Slot(int)
    def editProfile(self, index):
        if not 0 <= index < len(self.profiles):
            return
        profile = self.profiles[index]
        self.selectProfile(index + 1)
        self.editor_requested.emit(profile)

    @Slot(int)
    def requestDelete(self, index):
        if 0 <= index < len(self.profiles):
            self.selectProfile(index + 1)
            self.removeProfile()

    @Slot()
    def testProfile(self):
        self._test_values(self._state['source'], self._state['browser'], self._file_path)

    def _test_values(self, source, browser, file_path):
        if source == 'file':
            try:
                cookie_options(CookieProfile('test', 'test', 'file', cookie_file=file_path))
            except ValueError as error:
                self.update(message=str(error))
                return False
            self.update(message='Cookie 文件格式有效；开启后可用于解析和下载。')
        elif source == 'browser':
            try:
                cookie_options(CookieProfile('test', 'test', 'browser', browser=browser))
            except ValueError as error:
                self.update(message=str(error))
                return False
            self.update(message='将使用当前浏览器的登录状态；开启后在解析和下载时读取。')
        return True

    @Slot(str)
    def fileSelected(self, url):
        self._file_path = QUrl(url).toLocalFile()
        self.update(fileLabel='…/' + Path(self._file_path).name, source='file')
        if self._editor_session is not None:
            self._editor_session.set_file_path(self._file_path)

    def _build_profile(self, values, old=None):
        source = str(values.get('source', 'browser'))
        browser = str(values.get('browser', 'chrome'))
        domain = str(values.get('domain', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z0-9]+', domain):
            raise ValueError('请填写适用网站域名，例如 bilibili.com 或 x.com。')
        file_path = str(values.get('file_path', self._file_path)) if source == 'file' else ''
        now = datetime.now(timezone.utc).isoformat()
        default_name = (f"{domain or '网站'} - {(browser or '浏览器').capitalize()}"
                        if source == 'browser' else 'cookies.txt 配置')
        return CookieProfile(old.id if old else uuid.uuid4().hex,
                             str(values.get('name', '')).strip() or default_name,
                             source, browser, file_path, domain,
                             old.created_at if old else now, now,
                             str(values.get('browser_profile', '')) if source == 'browser' else '')

    @Slot('QVariantMap', result=bool)
    def saveEditor(self, values):
        old = next((p for p in self.profiles if p.id == values.get('id')), None)
        try:
            profile = self._build_profile(values, old)
            cookie_options(profile)
        except ValueError as error:
            self.update(message=str(error))
            return False
        profiles = tuple(item for item in self.profiles if item.id != profile.id) + (profile,)
        self._save_failed = False
        self.save_requested.emit(profiles)
        return not self._save_failed

    def mark_save_failed(self):
        self._save_failed = True
        self.update(message='Cookie 配置保存失败，原配置已保留。')

    @Slot()
    def saveProfile(self):
        if self._state['source'] == 'none':
            self.selectProfile(0)
            return
        self.saveEditor({'id': self.selected_profile.id if self.selected_profile else '',
                         'name': self._state['name'], 'domain': self._state['domain'],
                         'source': self._state['source'], 'browser': self._state['browser'],
                         'file_path': self._file_path})

    @Slot()
    def removeProfile(self):
        profile = self.selected_profile
        if profile:
            self.delete_requested.emit(profile)

    def apply_saved_profiles(self, profiles):
        self.set_profiles(profiles)
        self.selectProfile(0)
        self.update(message='Cookie 配置已保存。')

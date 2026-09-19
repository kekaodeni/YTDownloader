"""Explicit, reference-only Cookie profiles; never stores credential contents."""
from dataclasses import asdict
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import yt_dlp

from yt_downloader.core.models import CookieProfile

BROWSERS = ('chrome', 'edge', 'firefox', 'brave', 'opera', 'chromium')


class ReadOnlyCookieYoutubeDL(yt_dlp.YoutubeDL):
    def save_cookies(self):
        # YoutubeDL normally writes the cookiefile on close; user files are inputs only.
        pass


def cookie_options(profile):
    if profile is None or profile.source_type == 'none':
        return {}
    if profile.source_type == 'browser':
        if profile.browser not in BROWSERS:
            raise ValueError('不支持的浏览器 Cookie 来源。')
        return {'cookiesfrombrowser': (profile.browser,)}
    if profile.source_type != 'file':
        raise ValueError('无效的 Cookie 来源。')
    path = Path(profile.cookie_file)
    if not path.is_absolute() or not path.is_file():
        raise ValueError('Cookie 文件不存在，请重新选择。')
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Cookie 文件过大。')
    try:
        with path.open(encoding='utf-8-sig') as source:
            if not source.readline().startswith(('# Netscape HTTP Cookie File', '# HTTP Cookie File')):
                raise ValueError('需要 Netscape 格式的 cookies.txt。')
            for line in source:
                if not line.strip() or (line.startswith('#') and not line.startswith('#HttpOnly_')):
                    continue
                fields = line.rstrip('\r\n').split('\t')
                if len(fields) != 7 or fields[1] not in {'TRUE', 'FALSE'} or fields[3] not in {'TRUE', 'FALSE'}:
                    raise ValueError('Cookie 文件格式无效。')
                if fields[4] and not fields[4].isdigit():
                    raise ValueError('Cookie 文件有效期无效。')
                domain = fields[0].removeprefix('#HttpOnly_')
                if not domain or domain.startswith('.') != (fields[1] == 'TRUE') or not fields[2].startswith('/'):
                    raise ValueError('Cookie 文件域名或路径格式无效。')
    except (OSError, UnicodeError):
        raise ValueError('无法读取 Cookie 文件，请重新选择。') from None
    return {'cookiefile': str(path)}


def recommended_profile(profiles, url):
    host = (urlsplit(url).hostname or '').casefold()
    return next((profile for profile in profiles if profile.domain_hint and
                 (host == profile.domain_hint.casefold() or host.endswith('.' + profile.domain_hint.casefold()))), None)


class CookieProfileStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return ()
        payload = json.loads(self.path.read_text(encoding='utf-8'))
        if payload.get('schema_version') != 1 or not isinstance(payload.get('profiles'), list):
            raise ValueError('Cookie 配置文件格式无效。')
        profiles = tuple(CookieProfile(**item) for item in payload['profiles'])
        if len({profile.id for profile in profiles}) != len(profiles):
            raise ValueError('Cookie 配置标识重复。')
        return profiles

    def save(self, profiles):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as output:
            json.dump({'schema_version': 1, 'profiles': [asdict(item) for item in profiles]}, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)

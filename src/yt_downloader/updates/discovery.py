from __future__ import annotations

from collections.abc import Callable, Mapping
import time

from semver import Version

from yt_downloader.updates.models import UpdateRelease


RELEASE_REPOSITORY = 'kekaodeni/YTDownloader'
LATEST_RELEASE_API = f'https://api.github.com/repos/{RELEASE_REPOSITORY}/releases/latest'
RELEASES_API = f'https://api.github.com/repos/{RELEASE_REPOSITORY}/releases'


class UpdateDiscoveryService:
    def __init__(self, fetch_json: Callable, *, max_pages: int = 20, deadline_seconds: float = 60) -> None:
        self._fetch_json = fetch_json
        self.max_pages = max_pages
        self.deadline_seconds = deadline_seconds

    def check(self, current_version: str) -> tuple[UpdateRelease, ...]:
        started = time.monotonic()
        found = {}
        for page in range(1, self.max_pages + 1):
            payloads = self._fetch_json(f'{RELEASES_API}?per_page=100&page={page}')
            if time.monotonic() - started > self.deadline_seconds:
                raise TimeoutError('Release enumeration exceeded its deadline')
            if not isinstance(payloads, list) or len(payloads) > 100:
                raise ValueError('Release response must be a bounded JSON array')
            for payload in payloads:
                if not isinstance(payload, Mapping):
                    raise ValueError('Invalid release list entry')
                release = self._release(payload, current_version)
                if release:
                    if release.version in found and found[release.version] != release:
                        raise ValueError('Conflicting duplicate release version')
                    found[release.version] = release
            if len(payloads) < 100:
                return tuple(found[version] for version in sorted(found, reverse=True))
        raise ValueError('Release enumeration incomplete: page limit exceeded')

    @staticmethod
    def _release(payload: Mapping, current_version: str) -> UpdateRelease | None:
        if bool(payload.get('draft')) or bool(payload.get('prerelease')):
            return None
        tag = payload.get('tag_name')
        if not isinstance(tag, str) or not tag.startswith('v'):
            return None
        try:
            version = Version.parse(tag[1:])
        except ValueError:
            return None
        if version.build:
            return None
        if version.prerelease or version <= Version.parse(current_version.removeprefix('v')):
            return None
        assets = payload.get('assets')
        if not isinstance(assets, list):
            raise ValueError('Release assets are missing')
        urls = {}
        for item in assets:
            if isinstance(item, Mapping):
                name = item.get('name')
                if name in {'update-manifest.json', 'update-manifest.sig'} and name in urls:
                    raise ValueError('Duplicate update metadata asset')
                if isinstance(name, str):
                    urls[name] = item.get('browser_download_url')
        manifest = urls.get('update-manifest.json')
        signature = urls.get('update-manifest.sig')
        if not isinstance(manifest, str) or not isinstance(signature, str):
            raise ValueError('Release must contain exact manifest and detached signature assets')
        prefix = f'https://github.com/{RELEASE_REPOSITORY}/releases/download/{tag}/'
        if manifest != prefix + 'update-manifest.json' or signature != prefix + 'update-manifest.sig':
            raise ValueError('Update metadata must come from the official release repository')
        release_url = payload.get('html_url')
        expected_release = f'https://github.com/{RELEASE_REPOSITORY}/releases/tag/{tag}'
        if release_url != expected_release:
            raise ValueError('Release page must belong to the official release repository')
        return UpdateRelease(version, tag, manifest, signature, release_url)

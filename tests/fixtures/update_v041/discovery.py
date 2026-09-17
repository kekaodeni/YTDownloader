from __future__ import annotations

from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from semver import Version

from yt_downloader.updates.models import UpdateRelease


RELEASE_REPOSITORY = 'kekaodeni/YTDownloader'
LATEST_RELEASE_API = f'https://api.github.com/repos/{RELEASE_REPOSITORY}/releases/latest'


class UpdateDiscoveryService:
    def __init__(self, fetch_json: Callable[[str], Mapping]) -> None:
        self._fetch_json = fetch_json

    def check(self, current_version: str) -> UpdateRelease | None:
        payload = self._fetch_json(LATEST_RELEASE_API)
        if bool(payload.get('draft')) or bool(payload.get('prerelease')):
            return None
        tag = payload.get('tag_name')
        if not isinstance(tag, str) or not tag.startswith('v'):
            raise ValueError('Release tag is not a stable semantic version')
        version = Version.parse(tag[1:])
        if version.prerelease or version <= Version.parse(current_version.removeprefix('v')):
            return None
        assets = payload.get('assets')
        if not isinstance(assets, list):
            raise ValueError('Release assets are missing')
        urls = {
            item.get('name'): item.get('browser_download_url')
            for item in assets if isinstance(item, Mapping)
        }
        manifest = urls.get('update-manifest.json')
        signature = urls.get('update-manifest.sig')
        if not isinstance(manifest, str) or not isinstance(signature, str):
            raise ValueError('Release must contain exact manifest and detached signature assets')
        prefix = f'https://github.com/{RELEASE_REPOSITORY}/releases/download/{tag}/'
        if not manifest.startswith(prefix) or not signature.startswith(prefix):
            raise ValueError('Update metadata must come from the official release repository')
        release_url = payload.get('html_url')
        expected_release = f'https://github.com/{RELEASE_REPOSITORY}/releases/tag/{tag}'
        if release_url != expected_release:
            raise ValueError('Release page must belong to the official release repository')
        return UpdateRelease(version, tag, manifest, signature, release_url)

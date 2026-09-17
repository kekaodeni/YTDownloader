from __future__ import annotations

from collections.abc import Mapping
from typing import Callable
import time
import re
from urllib.parse import urljoin, urlsplit

import requests

from yt_downloader.services.network_policy import NetworkPolicy


class SecureUpdateHttpClient:
    """Credential-free HTTP client; system proxies are copied explicitly."""

    def __init__(self, network: NetworkPolicy, *, session_factory: Callable = requests.Session) -> None:
        self.network = network
        self.session_factory = session_factory

    def _session(self):
        snapshot = self.network.snapshot()
        session = self.session_factory()
        session.trust_env = False  # prevents .netrc credentials and implicit auth
        session.auth = None
        session.cookies.clear()
        session.headers.update({
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'YTDownloader-UpdateClient',
        })
        for sensitive in ('Authorization', 'Cookie'):
            session.headers.pop(sensitive, None)
        if snapshot.mode == 'system':
            session.proxies.update(snapshot.detected_proxies)
        elif snapshot.mode == 'custom':
            session.proxies.update({'http': snapshot.custom_proxy_url, 'https': snapshot.custom_proxy_url})
        return session

    def get_json(self, url: str) -> Mapping | list:
        base = 'https://api.github.com/repos/kekaodeni/YTDownloader/releases'
        is_list = re.fullmatch(re.escape(base) + r'\?per_page=100&page=([1-9]|1[0-9]|20)', url) is not None
        if not is_list and url != base + '/latest':
            raise ValueError('Update discovery URL is not trusted')
        session = self._session()
        response = None
        try:
            response = session.get(url, timeout=(10, 10), allow_redirects=False)
            response.raise_for_status()
            payload = response.json()
            if (is_list and (not isinstance(payload, list) or len(payload) > 100)) or (not is_list and not isinstance(payload, Mapping)):
                raise ValueError('Release response has invalid shape')
            return payload
        finally:
            if response is not None:
                response.close()
            session.close()

    def open_stream(self, url: str, timeout: tuple[int, int]):
        allowed = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
        session = self._session()
        response = None
        try:
            current = url
            for _redirect in range(4):
                parsed = urlsplit(current)
                if parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.username or parsed.password:
                    raise ValueError('Update redirect is not an approved HTTPS GitHub asset host')
                if parsed.port not in {None, 443}:
                    raise ValueError('Update HTTPS resources must use port 443')
                response = session.get(current, timeout=timeout, stream=True, allow_redirects=False)
                if response.status_code not in {301, 302, 303, 307, 308}:
                    response.raise_for_status()
                    return _StreamingResponse(response, session)
                location = response.headers.get('Location')
                response.close()
                response = None
                if not location:
                    raise ValueError('Update redirect has no location')
                current = urljoin(current, location)
            raise ValueError('Update redirect limit exceeded')
        except BaseException:
            if response is not None:
                response.close()
            session.close()
            raise

    def get_bytes(self, url: str, *, max_bytes: int = 1024 * 1024) -> bytes:
        if max_bytes <= 0:
            raise ValueError('Update metadata size limit must be positive')
        started = time.monotonic()
        stream = self.open_stream(url, (10, 10))
        chunks: list[bytes] = []
        length = 0
        try:
            for chunk in stream.iter_content(64 * 1024):
                if time.monotonic() - started > 20:
                    raise TimeoutError('Update metadata exceeded its 20 second deadline')
                if not chunk:
                    continue
                length += len(chunk)
                if length > max_bytes:
                    raise ValueError('Update metadata is too large')
                chunks.append(chunk)
            return b''.join(chunks)
        finally:
            stream.close()


class _StreamingResponse:
    def __init__(self, response, session) -> None:
        self.response = response
        self.session = session

    def iter_content(self, size: int):
        return self.response.iter_content(size)

    def close(self) -> None:
        self.response.close()
        self.session.close()

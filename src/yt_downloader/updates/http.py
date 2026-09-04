from __future__ import annotations

from collections.abc import Mapping
from typing import Callable

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

    def get_json(self, url: str) -> Mapping:
        if url != 'https://api.github.com/repos/kekaodeni/YTDownloader-releases/releases/latest':
            raise ValueError('Update discovery URL is not trusted')
        session = self._session()
        response = None
        try:
            response = session.get(url, timeout=(10, 10), allow_redirects=False)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise ValueError('Release response must be a JSON object')
            return payload
        finally:
            if response is not None:
                response.close()
            session.close()

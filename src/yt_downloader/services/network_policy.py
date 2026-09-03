"""One runtime-resolved proxy policy shared by every network operation."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable, Mapping
from urllib.parse import urlsplit
from urllib.request import getproxies

import requests

from yt_downloader.core.errors import AppError, ErrorContext


_MODES = {"system", "direct", "custom"}
_CUSTOM_SCHEMES = {"http", "https", "socks4", "socks5", "socks5h"}


def _validate_custom_proxy(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in _CUSTOM_SCHEMES or not parsed.hostname:
        raise ValueError("自定义代理必须是有效的 HTTP、HTTPS 或 SOCKS URL。")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("自定义代理端口无效。") from exc
    return candidate


def _safe_proxy(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or "未知主机"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""
    return f"{parsed.scheme.lower()}://{host}{port}"


@dataclass(frozen=True, slots=True)
class NetworkSnapshot:
    mode: str
    custom_proxy_url: str
    detected_proxies: Mapping[str, str]
    safe_description: str


@dataclass(frozen=True, slots=True)
class NetworkTestResult:
    elapsed_seconds: float
    description: str


class NetworkPolicy:
    def __init__(
        self,
        mode: str = "system",
        custom_proxy_url: str = "",
        *,
        proxy_resolver: Callable[[], Mapping[str, str]] = getproxies,
        session_factory: Callable[[], requests.Session] = requests.Session,
    ) -> None:
        self._lock = threading.RLock()
        self._proxy_resolver = proxy_resolver
        self._session_factory = session_factory
        self.configure(mode, custom_proxy_url)

    def configure(self, mode: str, custom_proxy_url: str = "") -> None:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in _MODES:
            raise ValueError("代理模式无效。")
        if normalized_mode == "custom":
            custom_proxy_url = _validate_custom_proxy(custom_proxy_url)
        with self._lock:
            self._mode = normalized_mode
            self._custom_proxy_url = custom_proxy_url.strip()

    def snapshot(self) -> NetworkSnapshot:
        with self._lock:
            mode = self._mode
            custom = self._custom_proxy_url
        if mode == "system":
            detected = {
                str(key): str(value)
                for key, value in self._proxy_resolver().items()
                if isinstance(value, str) and value
            }
            if detected:
                safe = "系统代理：" + ", ".join(
                    f"{key}={_safe_proxy(value)}" for key, value in sorted(detected.items())
                )
            else:
                safe = "系统代理：未检测到显式代理（可能为直连或 TUN）"
            return NetworkSnapshot(mode, "", detected, safe)
        if mode == "direct":
            return NetworkSnapshot(mode, "", {}, "直连（忽略系统代理）")
        custom = _validate_custom_proxy(custom)
        return NetworkSnapshot(mode, custom, {}, f"自定义代理：{_safe_proxy(custom)}")

    def ytdlp_options(self) -> dict[str, str]:
        snapshot = self.snapshot()
        if snapshot.mode == "direct":
            return {"proxy": ""}
        if snapshot.mode == "custom":
            return {"proxy": snapshot.custom_proxy_url}
        # Omitting the option lets yt-dlp resolve the current environment,
        # Windows Internet Settings, or a TUN/full-tunnel route for each task.
        return {}

    def get(self, url: str, **kwargs):
        snapshot = self.snapshot()
        session = self._session_factory()
        session.trust_env = snapshot.mode == "system"
        if snapshot.mode == "custom":
            kwargs["proxies"] = {
                "http": snapshot.custom_proxy_url,
                "https": snapshot.custom_proxy_url,
            }
        try:
            return session.get(url, **kwargs)
        finally:
            session.close()

    def test_connection(self, url: str = "https://www.youtube.com/robots.txt") -> NetworkTestResult:
        started = time.monotonic()
        try:
            response = self.get(url, timeout=15, headers={"User-Agent": "YTDownloader/0.2"})
            response.raise_for_status()
            return NetworkTestResult(time.monotonic() - started, self.snapshot().safe_description)
        except requests.RequestException as exc:
            raise AppError(
                "network_test_failed",
                "连接测试失败，请检查代理设置和网络连接。",
                repr(exc),
                ErrorContext(stage="Testing network connection"),
            ) from exc

import pytest

from yt_downloader.services.network_policy import NetworkPolicy


def test_system_proxy_is_resolved_per_task_without_hardcoded_injection() -> None:
    detected = {"http": "http://127.0.0.1:1111"}
    policy = NetworkPolicy("system", proxy_resolver=lambda: dict(detected))

    first = policy.snapshot()
    detected["http"] = "http://127.0.0.1:2222"
    second = policy.snapshot()

    assert first.detected_proxies["http"].endswith(":1111")
    assert second.detected_proxies["http"].endswith(":2222")
    assert policy.ytdlp_options() == {}


def test_direct_and_custom_proxy_modes_map_to_yt_dlp_safely() -> None:
    direct = NetworkPolicy("direct")
    assert direct.ytdlp_options() == {"proxy": ""}

    custom = NetworkPolicy("custom", "http://user:secret@127.0.0.1:8899")
    assert custom.ytdlp_options() == {"proxy": "http://user:secret@127.0.0.1:8899"}
    assert "secret" not in custom.snapshot().safe_description
    assert "user" not in custom.snapshot().safe_description
    assert "127.0.0.1:8899" in custom.snapshot().safe_description


@pytest.mark.parametrize(
    "value",
    ["", "127.0.0.1:8080", "ftp://127.0.0.1:21", "http://:bad"],
)
def test_custom_proxy_rejects_invalid_or_unsupported_urls(value: str) -> None:
    with pytest.raises(ValueError):
        NetworkPolicy("custom", value).snapshot()

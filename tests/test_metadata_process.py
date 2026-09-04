from __future__ import annotations

import time

from yt_downloader.core.models import CodecPreference, ParseState
from yt_downloader.workers.metadata_process import (
    MetadataProcessConfig,
    MetadataProcessController,
)
from yt_downloader.workers.request_gate import RequestToken


def _blocking_entry(send_connection, cancel_event, _url, _config) -> None:
    while not cancel_event.is_set():
        time.sleep(0.05)
    time.sleep(60)


def _broken_entry(send_connection, _cancel_event, _url, _config) -> None:
    send_connection.close()


def test_user_cancel_terminates_a_blocked_metadata_process_within_two_seconds(
    qtbot,
) -> None:
    controller = MetadataProcessController(
        entrypoint=_blocking_entry,
        force_cancel_ms=100,
        soft_timeout_ms=10_000,
        hard_timeout_ms=20_000,
    )
    token = RequestToken(1, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    config = MetadataProcessConfig(
        deno_path="",
        proxy_mode="direct",
        custom_proxy_url="",
        codec_preference=CodecPreference.AUTO,
        require_deno=False,
    )
    controller.start(token, token.source, config)
    assert controller.state is ParseState.RUNNING

    started = time.monotonic()
    with qtbot.waitSignal(controller.cancelled, timeout=2_000) as signal:
        controller.cancel()

    assert signal.args == [token]
    assert time.monotonic() - started < 2
    assert controller.state is ParseState.CANCELLED
    assert not controller.is_running


def test_hard_timeout_is_terminal_and_restores_controller(qtbot) -> None:
    controller = MetadataProcessController(
        entrypoint=_blocking_entry,
        force_cancel_ms=50,
        soft_timeout_ms=50,
        hard_timeout_ms=150,
    )
    token = RequestToken(2, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    config = MetadataProcessConfig(
        deno_path="",
        proxy_mode="direct",
        custom_proxy_url="",
        codec_preference=CodecPreference.AUTO,
        require_deno=False,
    )

    with qtbot.waitSignal(controller.timed_out, timeout=2_000) as signal:
        controller.start(token, token.source, config)

    assert signal.args[0] == token
    assert signal.args[1].code == "metadata_timed_out"
    assert controller.state is ParseState.TIMED_OUT
    assert not controller.is_running


def test_broken_ipc_becomes_a_localized_failure(qtbot) -> None:
    controller = MetadataProcessController(entrypoint=_broken_entry)
    token = RequestToken(3, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    config = MetadataProcessConfig(
        deno_path="",
        proxy_mode="direct",
        custom_proxy_url="",
        codec_preference=CodecPreference.AUTO,
        require_deno=False,
    )

    with qtbot.waitSignal(controller.failed, timeout=2_000) as signal:
        controller.start(token, token.source, config)

    assert signal.args[0] == token
    assert signal.args[1].user_message == "解析进程意外结束，请重试。"
    assert controller.state is ParseState.FAILED

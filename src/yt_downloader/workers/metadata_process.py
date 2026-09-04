"""Cancellable metadata extraction in a task-scoped helper process."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import multiprocessing
from multiprocessing.connection import Connection
from pathlib import Path
import time
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Signal

from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.core.models import CodecPreference, ParseState
from yt_downloader.infrastructure.windows_job import ProcessJob
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.network_policy import NetworkPolicy
from yt_downloader.services.youtube_service import YoutubeService
from yt_downloader.workers.request_gate import RequestToken


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MetadataProcessConfig:
    deno_path: str
    proxy_mode: str
    custom_proxy_url: str
    codec_preference: CodecPreference
    require_deno: bool = True


def metadata_process_self_test_entry(
    _send_connection: Connection,
    _cancel_event: Any,
    _url: str,
    _config: MetadataProcessConfig,
) -> None:
    """Importable blocking target used to validate frozen spawn/termination."""
    while True:
        time.sleep(1)


def _serialize_error(error: AppError) -> dict[str, Any]:
    return {
        "code": error.code,
        "user_message": error.user_message,
        "technical_message": redact_sensitive(error.technical_message),
        "context": {
            "url": error.context.url,
            "selected_format": error.context.selected_format,
            "output_directory": error.context.output_directory,
            "stage": error.context.stage,
            "traceback_text": redact_sensitive(error.context.traceback_text),
            "log_excerpt": redact_sensitive(error.context.log_excerpt),
        },
    }


def _deserialize_error(payload: dict[str, Any]) -> AppError:
    context = payload.get("context") or {}
    return AppError(
        str(payload.get("code") or "metadata_failed"),
        str(payload.get("user_message") or "无法获取该视频的信息。"),
        redact_sensitive(str(payload.get("technical_message") or "Unknown helper error")),
        ErrorContext(
            url=str(context.get("url") or ""),
            selected_format=str(context.get("selected_format") or ""),
            output_directory=str(context.get("output_directory") or ""),
            stage=str(context.get("stage") or "Fetching metadata"),
            traceback_text=redact_sensitive(str(context.get("traceback_text") or "")),
            log_excerpt=redact_sensitive(str(context.get("log_excerpt") or "")),
        ),
    )


def metadata_process_entry(
    send_connection: Connection,
    cancel_event: Any,
    url: str,
    config: MetadataProcessConfig,
) -> None:
    """Process entrypoint kept importable for PyInstaller spawn children."""
    try:
        network = NetworkPolicy(config.proxy_mode, config.custom_proxy_url)
        service = YoutubeService(
            deno_path=Path(config.deno_path) if config.deno_path else None,
            require_deno=config.require_deno,
            network_policy=network,
            codec_preference=config.codec_preference,
        )
        video = service.fetch_metadata(url, cancel_event, include_thumbnail=False)
        send_connection.send(("result", video))
    except OperationCancelled:
        send_connection.send(("cancelled", None))
    except AppError as error:
        send_connection.send(("error", _serialize_error(error)))
    except BaseException as error:
        safe = redact_sensitive(repr(error))
        send_connection.send(("error", _serialize_error(AppError(
            "metadata_helper_failed",
            "解析进程意外结束，请重试。",
            safe,
            ErrorContext(url=url, stage="Metadata helper process"),
        ))))
    finally:
        send_connection.close()


class MetadataProcessController(QObject):
    result = Signal(object, object)
    failed = Signal(object, object)
    cancelled = Signal(object)
    timed_out = Signal(object, object)
    state_changed = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        entrypoint: Callable[..., None] = metadata_process_entry,
        poll_interval_ms: int = 40,
        force_cancel_ms: int = 300,
        soft_timeout_ms: int = 18_000,
        hard_timeout_ms: int = 45_000,
    ) -> None:
        super().__init__(parent)
        self._entrypoint = entrypoint
        self._force_cancel_ms = force_cancel_ms
        self._soft_timeout_ms = soft_timeout_ms
        self._hard_timeout_ms = hard_timeout_ms
        self._context = multiprocessing.get_context("spawn")
        self._process: multiprocessing.Process | None = None
        self._receive: Connection | None = None
        self._cancel_event: Any = None
        self._job: ProcessJob | None = None
        self._token: RequestToken | None = None
        self._outcome: tuple[str, Any] | None = None
        self._timed_out = False
        self._shutdown = False
        self.state = ParseState.IDLE
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(poll_interval_ms)
        self._poll_timer.timeout.connect(self._poll)
        self._soft_timer = QTimer(self)
        self._soft_timer.setSingleShot(True)
        self._soft_timer.timeout.connect(self._mark_slow)
        self._hard_timer = QTimer(self)
        self._hard_timer.setSingleShot(True)
        self._hard_timer.timeout.connect(self._timeout)

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self, token: RequestToken, url: str, config: MetadataProcessConfig) -> None:
        if self._process is not None:
            self.cancel()
            self._force_stop()
            self._finish_dead_process()
        self._shutdown = False
        self._token = token
        self._outcome = None
        self._timed_out = False
        receive, send = self._context.Pipe(duplex=False)
        cancel_event = self._context.Event()
        process = self._context.Process(
            target=self._entrypoint,
            args=(send, cancel_event, url, config),
            name=f"YTDownloaderMetadata-{token.generation}",
            daemon=False,
        )
        self._receive = receive
        self._cancel_event = cancel_event
        self._process = process
        process.start()
        send.close()
        self._job = ProcessJob()
        self._job.assign(process.pid)
        self._set_state(ParseState.RUNNING)
        self._poll_timer.start()
        self._soft_timer.start(self._soft_timeout_ms)
        self._hard_timer.start(self._hard_timeout_ms)

    def cancel(self) -> None:
        if self._process is None or self.state not in {ParseState.RUNNING, ParseState.SLOW}:
            return
        self._set_state(ParseState.CANCELLING)
        if self._cancel_event is not None:
            self._cancel_event.set()
        QTimer.singleShot(self._force_cancel_ms, self._force_stop)

    def _mark_slow(self) -> None:
        if self.state is ParseState.RUNNING:
            self._set_state(ParseState.SLOW)

    def _timeout(self) -> None:
        if self.state not in {ParseState.RUNNING, ParseState.SLOW}:
            return
        self._timed_out = True
        self._set_state(ParseState.CANCELLING)
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._force_stop()

    def _force_stop(self) -> None:
        process = self._process
        if process is None or not process.is_alive():
            self._poll()
            return
        if not (self._job and self._job.terminate()):
            process.terminate()
            process.join(timeout=0.15)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(timeout=0.15)
            if process.is_alive() and process.pid:
                ProcessJob.terminate_process(process.pid)
        process.join(timeout=0.5)
        self._poll()

    def _poll(self) -> None:
        receive = self._receive
        if receive is not None and self._outcome is None:
            try:
                if receive.poll():
                    self._outcome = receive.recv()
            except (EOFError, OSError) as error:
                self._outcome = ("broken", redact_sensitive(repr(error)))
        process = self._process
        if process is not None and not process.is_alive():
            self._finish_dead_process()

    def _finish_dead_process(self) -> None:
        process = self._process
        token = self._token
        if process is None or token is None:
            return
        process.join(timeout=0.2)
        state_before_cleanup = self.state
        outcome = self._outcome
        self._cleanup_handles()
        if self._shutdown:
            self._set_state(ParseState.IDLE)
            return
        if self._timed_out:
            error = AppError(
                "metadata_timed_out",
                "解析超时，请检查网络或代理后重试。",
                "Metadata helper exceeded the 45 second hard timeout",
                ErrorContext(url=token.source, stage="Fetching metadata"),
            )
            self._set_state(ParseState.TIMED_OUT)
            self.timed_out.emit(token, error)
        elif state_before_cleanup is ParseState.CANCELLING or (outcome and outcome[0] == "cancelled"):
            self._set_state(ParseState.CANCELLED)
            self.cancelled.emit(token)
        elif outcome and outcome[0] == "result":
            self._set_state(ParseState.SUCCEEDED)
            self.result.emit(token, outcome[1])
        elif outcome and outcome[0] == "error":
            self._set_state(ParseState.FAILED)
            self.failed.emit(token, _deserialize_error(outcome[1]))
        else:
            detail = outcome[1] if outcome else f"helper exit code {process.exitcode}"
            self._set_state(ParseState.FAILED)
            self.failed.emit(token, AppError(
                "metadata_helper_failed",
                "解析进程意外结束，请重试。",
                redact_sensitive(str(detail)),
                ErrorContext(url=token.source, stage="Metadata helper process"),
            ))

    def _cleanup_handles(self) -> None:
        self._poll_timer.stop()
        self._soft_timer.stop()
        self._hard_timer.stop()
        if self._receive is not None:
            self._receive.close()
        if self._job is not None:
            self._job.close()
        self._receive = None
        self._cancel_event = None
        self._process = None
        self._job = None
        self._outcome = None

    def _set_state(self, state: ParseState) -> None:
        self.state = state
        self.state_changed.emit(state)

    def shutdown(self) -> None:
        self._shutdown = True
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._force_stop()
        process = self._process
        if process is not None:
            process.join(timeout=1.0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.5)
        self._cleanup_handles()
        self._token = None
        self._set_state(ParseState.IDLE)


def run_metadata_process_self_test(app: QObject) -> int:
    """Exercise frozen helper spawn, cancel, timeout and child cleanup."""
    config = MetadataProcessConfig(
        "", "direct", "", CodecPreference.AUTO, require_deno=False
    )
    cancel_controller = MetadataProcessController(
        app,
        entrypoint=metadata_process_self_test_entry,
        force_cancel_ms=100,
        soft_timeout_ms=2_000,
        hard_timeout_ms=3_000,
    )
    timeout_controller = MetadataProcessController(
        app,
        entrypoint=metadata_process_self_test_entry,
        force_cancel_ms=50,
        soft_timeout_ms=50,
        hard_timeout_ms=180,
    )
    outcome = {"exit_code": 9}

    def fail() -> None:
        outcome["exit_code"] = 2
        app.exit(2)  # type: ignore[attr-defined]

    def start_timeout(_token: RequestToken) -> None:
        if cancel_controller.is_running:
            fail()
            return
        timeout_controller.start(
            RequestToken(2, "selftest-timeout"), "selftest-timeout", config
        )

    def finish_timeout(_token: RequestToken, _error: AppError) -> None:
        if timeout_controller.is_running:
            fail()
            return
        outcome["exit_code"] = 0
        app.exit(0)  # type: ignore[attr-defined]

    cancel_controller.cancelled.connect(start_timeout)
    cancel_controller.failed.connect(lambda *_args: fail())
    cancel_controller.timed_out.connect(lambda *_args: fail())
    timeout_controller.timed_out.connect(finish_timeout)
    timeout_controller.failed.connect(lambda *_args: fail())
    timeout_controller.cancelled.connect(lambda *_args: fail())
    cancel_controller.start(
        RequestToken(1, "selftest-cancel"), "selftest-cancel", config
    )
    QTimer.singleShot(100, cancel_controller.cancel)
    QTimer.singleShot(5_000, fail)
    app.exec()  # type: ignore[attr-defined]
    cancel_controller.shutdown()
    timeout_controller.shutdown()
    return int(outcome["exit_code"])

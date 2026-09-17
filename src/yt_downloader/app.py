"""Application composition root. Services and Qt pages meet only here."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from dataclasses import replace
import json
import logging
from pathlib import Path
import os
import subprocess
import sys
import threading
import uuid

from PySide6.QtCore import QLocale, QThreadPool, QTimer, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
import yt_dlp.version

from yt_downloader import __version__
from yt_downloader.core.errors import AppError, ErrorContext
from yt_downloader.core.filename import sanitize_filename
from yt_downloader.core.models import DownloadProgress, DownloadRequest, FormatOption, HistoryRecord, ParseState, TaskStatus, VideoInfo
from yt_downloader.infrastructure.logging_config import configure_logging, install_exception_hook
from yt_downloader.infrastructure.paths import AppPaths, default_videos_directory
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.infrastructure.shell import open_path, reveal_in_folder
from yt_downloader.infrastructure.system_info import build_system_info
from yt_downloader.infrastructure.self_test import run_packaged_self_test
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.error_report_service import build_error_report
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.history_service import HistoryDeleteResult, HistoryRepository
from yt_downloader.services.network_policy import NetworkPolicy, NetworkTestResult
from yt_downloader.services.settings_service import SettingsService
from yt_downloader.services.youtube_service import YoutubeService
from yt_downloader.ui.quick_window import MainWindow
from yt_downloader.ui.progress_dispatch import ProgressEventCoalescer
from yt_downloader.ui.localization import install_qt_zh_cn_translator
from yt_downloader.ui.quick_theme import QuickTheme as ThemeManager
from yt_downloader.ui.typography import application_font, install_typography_manager, resolve_font_families
from yt_downloader.ui.quick_dialogs import ErrorSession as ErrorDialog
from yt_downloader.ui.quick_cover import CoverSession as ThumbnailDialog
from yt_downloader.workers.download_queue import DownloadQueueController
from yt_downloader.workers.function_worker import FunctionWorker
from yt_downloader.workers.metadata_process import (
    MetadataProcessConfig,
    MetadataProcessController,
    run_metadata_process_self_test,
)
from yt_downloader.workers.request_gate import LatestRequestGate, RequestToken
from yt_downloader.updates.discovery import UpdateDiscoveryService
from yt_downloader.updates.download import UpdatePackageDownloader
from yt_downloader.updates.http import SecureUpdateHttpClient
from yt_downloader.updates.models import UpdateCapability, UpdateState
from yt_downloader.updates.service import UpdateService
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.state import UpdateStateStore, detect_update_capability
from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS
from yt_downloader.ui.quick_dialogs import UpdateSession as UpdateDialog


logger = logging.getLogger(__name__)


class _MemoryHistory:
    """Keeps the main window usable if the local database is damaged or locked."""
    def __init__(self) -> None:
        self.records: dict[str, HistoryRecord] = {}

    def upsert(self, record: HistoryRecord) -> None:
        self.records[record.task_id] = record

    def update_status(self, task_id, status, **values) -> None:
        from dataclasses import replace
        if task_id in self.records:
            allowed = {key: value for key, value in values.items() if value is not None}
            self.records[task_id] = replace(self.records[task_id], status=status, **allowed)

    def update_thumbnail(self, task_id, thumbnail_path) -> None:
        from dataclasses import replace
        if task_id in self.records:
            self.records[task_id] = replace(
                self.records[task_id],
                thumbnail_path=Path(thumbnail_path) if thumbnail_path else None,
            )

    def get(self, task_id: str) -> HistoryRecord | None:
        return self.records.get(task_id)

    def delete(self, task_id: str) -> bool:
        return self.records.pop(task_id, None) is not None

    def delete_many(self, task_ids) -> HistoryDeleteResult:
        unique_ids = tuple(dict.fromkeys(task_ids))
        deleted = 0
        for task_id in unique_ids:
            record = self.records.get(task_id)
            if record and record.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                self.records.pop(task_id, None)
                deleted += 1
        return HistoryDeleteResult(deleted, len(unique_ids) - deleted)

    def clear_terminal(self) -> HistoryDeleteResult:
        deletable = tuple(
            task_id for task_id, record in self.records.items()
            if record.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        )
        for task_id in deletable:
            self.records.pop(task_id, None)
        return HistoryDeleteResult(len(deletable), len(self.records))

    def mark_interrupted(self) -> int:
        return 0

    def list_records(self, *, limit=500):
        return list(reversed(list(self.records.values())))[:limit]


class AppController:
    def __init__(self, app: QApplication, paths: AppPaths, *, debug: bool = False) -> None:
        self.app = app
        self.paths = paths
        self.settings_service = SettingsService(paths.settings, default_download_directory=default_videos_directory())
        self.settings = self.settings_service.load()
        self.theme = ThemeManager(app)
        self.theme.set_mode(self.settings.theme)
        try:
            self.history = HistoryRepository(paths.history)
            interrupted = self.history.mark_interrupted()
            if interrupted:
                logger.warning("Marked %d unfinished task(s) as interrupted", interrupted)
        except Exception:
            logger.exception("History database unavailable; using in-memory history")
            self.history = _MemoryHistory()
        self.ffmpeg = FfmpegService(configured_directory=self.settings.ffmpeg_directory or None)
        self.deno_path = find_tool("deno")
        self.network = NetworkPolicy(self.settings.proxy_mode, self.settings.custom_proxy_url)
        self.youtube = YoutubeService(
            deno_path=self.deno_path,
            network_policy=self.network,
            codec_preference=self.settings.codec_preference,
        )
        self.download_service = DownloadService(
            deno_path=self.deno_path,
            ffmpeg_path=self.ffmpeg.ffmpeg_path,
            network_policy=self.network,
            concurrent_fragments=self.settings.concurrent_fragments,
        )
        ffmpeg_description = str(self.ffmpeg.ffmpeg_path) if self.ffmpeg.ffmpeg_path else "未找到"
        self.window = MainWindow(
            self.settings,
            ytdlp_version=yt_dlp.version.__version__,
            ffmpeg_description=ffmpeg_description,
            theme=self.theme,
        )
        self.window.history_page.configure_thumbnails(self.ffmpeg, self.paths.cache / "history-previews")
        self.queue = DownloadQueueController(self.download_service, self.window)
        self.metadata_process = MetadataProcessController(self.window)
        self._thumbnail_cancel: threading.Event | None = None
        self._thumbnail_workers: list[FunctionWorker] = []
        self._settings_workers: list[FunctionWorker] = []
        self._metadata_gate: LatestRequestGate[object] = LatestRequestGate()
        self._thumbnail_gate: LatestRequestGate[object] = LatestRequestGate()
        self._pending_retry: HistoryRecord | DownloadRequest | None = None
        self._remove_intents: set[str] = set()
        self._dialogs: list[object] = []
        self._persisted_task_stages: dict[str, TaskStatus] = {}
        self._progress_dispatch = ProgressEventCoalescer(self.window)
        self.update_http = SecureUpdateHttpClient(self.network)
        self.update_capability = detect_update_capability(trusted_keys=PRODUCTION_TRUSTED_KEYS)
        self.updates = UpdateService(
            current_version=__version__,
            discovery=UpdateDiscoveryService(self.update_http.get_json),
            fetch_bytes=self.update_http.get_bytes,
            keyring=TrustedKeyring(PRODUCTION_TRUSTED_KEYS),
            state_store=UpdateStateStore(paths.update_state),
            downloader=UpdatePackageDownloader(self.update_http.open_stream),
            staging_root=paths.update_staging,
            capability=self.update_capability,
            backup_size=self._installed_tree_size,
        )
        self._update_dialog: UpdateDialog | None = None
        self._update_install_pending = False
        self._wire()
        self.refresh_history()
        restored_update = self.updates.restore_verified_package()
        persisted_update = self.updates.state_store.load()
        if persisted_update.last_checked_at and not restored_update:
            self.window.settings_page.set_update_state(f"上次检查：{persisted_update.last_checked_at}")
        clipboard = QGuiApplication.clipboard().text().strip()
        if clipboard:
            self.window.download_page.set_clipboard_hint(clipboard)
        if self.settings.auto_check_updates and not restored_update:
            QTimer.singleShot(10_000, lambda: self.updates.check(manual=False))

    def _wire(self) -> None:
        download = self.window.download_page
        download.parse_requested.connect(self.fetch_metadata)
        download.parse_cancel_requested.connect(self.metadata_process.cancel)
        download.download_requested.connect(self.enqueue_download)
        download.cancel_requested.connect(self.queue.cancel)
        download.open_file_requested.connect(self._open_file)
        download.open_folder_requested.connect(self._reveal_file)
        download.remove_requested.connect(self._remove_task_requested)
        download.retry_requested.connect(self._retry_task)
        history = self.window.history_page
        history.open_file_requested.connect(self._open_file)
        history.open_folder_requested.connect(self._reveal_file)
        history.copy_link_requested.connect(lambda value: QGuiApplication.clipboard().setText(value))
        history.thumbnail_requested.connect(self._change_thumbnail)
        history.retry_requested.connect(self._retry_record)
        history.delete_requested.connect(self._delete_history_record)
        history.delete_many_requested.connect(self._delete_history_records)
        history.clear_terminal_requested.connect(self._clear_terminal_history)
        settings = self.window.settings_page
        settings.save_requested.connect(self.save_settings)
        settings.network_test_requested.connect(self.test_network_connection)
        settings.theme_preview_requested.connect(self.theme.set_mode)
        self.theme.theme_changed.connect(self.window.apply_theme)
        settings.open_logs_requested.connect(lambda: self._open_directory(self.paths.logs))
        settings.copy_system_info_requested.connect(self.copy_system_info)
        settings.update_check_requested.connect(lambda: self.updates.check(manual=True))
        self.queue.task_queued.connect(download.add_task)
        self.queue.task_started.connect(download.task_started)
        self.queue.cancelling.connect(self._cancelling)
        self.queue.progress.connect(self._progress_dispatch.push)
        self._progress_dispatch.dispatched.connect(self._progress)
        self.queue.completed.connect(self._completed)
        self.queue.failed.connect(self._failed)
        self.queue.cancelled.connect(self._cancelled)
        self.queue.busy_changed.connect(self.window.set_download_busy)
        self.window.cancel_all_requested.connect(self.queue.cancel_all)
        self.window.cancel_update_requested.connect(self.updates.cancel)
        self.metadata_process.state_changed.connect(download.set_parse_state)
        self.metadata_process.result.connect(self._metadata_result)
        self.metadata_process.failed.connect(self._metadata_error)
        self.metadata_process.timed_out.connect(self._metadata_error)
        self.metadata_process.cancelled.connect(self._metadata_cancelled)
        self.app.aboutToQuit.connect(self._shutdown_background_operations)
        self.window.show_update_requested.connect(self._show_update_dialog)
        self.updates.state_changed.connect(self._update_state_changed)
        self.updates.install_prepared.connect(self._launch_prepared_updater)
        self.updates.update_available.connect(self._update_available)
        self.updates.up_to_date.connect(lambda: self.window.settings_page.set_update_state("已是最新版本"))
        self.updates.progress.connect(self._update_progress)
        self.updates.ready.connect(self._update_ready)
        self.updates.failed.connect(self._update_failed)

    def fetch_metadata(self, url: str) -> None:
        self._cancel_thumbnail()
        token = self._metadata_gate.begin(url.strip())
        self.metadata_process.start(token, url, MetadataProcessConfig(
            deno_path=str(self.deno_path or ""),
            proxy_mode=self.settings.proxy_mode,
            custom_proxy_url=self.settings.custom_proxy_url,
            codec_preference=self.settings.codec_preference,
            require_deno=True,
        ))

    def _metadata_result(self, token: RequestToken, video) -> None:
        if not self._metadata_gate.deliver(token, self._apply_metadata_result, video):
            return
        self._metadata_gate.finish(token)
        self._start_thumbnail(video)

    def _apply_metadata_result(self, video) -> None:
        retry = self._pending_retry
        preferred = (
            retry.format.label if isinstance(retry, DownloadRequest)
            else retry.quality_label if retry else self.settings.default_quality
        )
        self.window.download_page.show_video(video, preferred_quality=preferred)
        if retry:
            self._pending_retry = None
            self.window.download_page.set_retry_defaults(
                retry.filename_stem if isinstance(retry, DownloadRequest) else retry.file_path.stem or video.title,
                str(retry.output_directory if isinstance(retry, DownloadRequest) else retry.file_path.parent),
            )

    def _metadata_error(self, token: RequestToken, error: AppError) -> None:
        if self._metadata_gate.deliver(token, self._apply_metadata_error, error):
            self._metadata_gate.finish(token)

    def _metadata_cancelled(self, token: RequestToken) -> None:
        if self._metadata_gate.finish(token):
            self._pending_retry = None

    def _start_thumbnail(self, video: VideoInfo) -> None:
        if not video.thumbnail_url:
            return
        token = self._thumbnail_gate.begin(video.url)
        cancel = threading.Event()
        self._thumbnail_cancel = cancel
        worker = FunctionWorker(self.youtube.fetch_thumbnail, video.thumbnail_url, cancel)
        self._thumbnail_workers.append(worker)
        worker.signals.result.connect(
            lambda data, current=token, video_id=video.video_id: self._thumbnail_result(
                current, video_id, data
            )
        )
        worker.signals.error.connect(
            lambda error, current=token: self._thumbnail_error(current, error)
        )
        worker.signals.finished.connect(
            lambda current_worker=worker, current=token: self._thumbnail_finished(
                current_worker, current
            )
        )
        QThreadPool.globalInstance().start(worker)

    def _thumbnail_result(self, token: RequestToken, video_id: str, data: bytes) -> None:
        if self._thumbnail_gate.is_current(token):
            self.window.download_page.set_thumbnail(video_id, data)

    def _thumbnail_error(self, token: RequestToken, error: AppError) -> None:
        if self._thumbnail_gate.is_current(token):
            logger.warning("Thumbnail request failed without failing metadata: %s", error.technical_message)

    def _thumbnail_finished(self, worker: FunctionWorker, token: RequestToken) -> None:
        if worker in self._thumbnail_workers:
            self._thumbnail_workers.remove(worker)
        if self._thumbnail_gate.finish(token):
            self._thumbnail_cancel = None

    def _cancel_thumbnail(self) -> None:
        if self._thumbnail_cancel is not None:
            self._thumbnail_cancel.set()
        self._thumbnail_cancel = None
        self._thumbnail_gate.current = None

    def _shutdown_background_operations(self) -> None:
        self._cancel_thumbnail()
        self.metadata_process.shutdown()
        self.updates.cancel()

    def _installed_tree_size(self) -> int:
        if not getattr(sys, 'frozen', False):
            return 0
        root = Path(sys.executable).parent
        try:
            return sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
        except OSError:
            return 0

    def _update_state_changed(self, state: UpdateState) -> None:
        labels = {
            UpdateState.IDLE: "尚未检查", UpdateState.CHECKING: "正在检查…",
            UpdateState.UP_TO_DATE: "已是最新版本", UpdateState.AVAILABLE: "发现新版本",
            UpdateState.NO_COMPATIBLE_UPDATE: "有更新版本，但当前更新组件不兼容，请查看发布说明。",
            UpdateState.DOWNLOADING: "正在下载更新…", UpdateState.CANCELLING: "正在取消更新…",
            UpdateState.VERIFYING: "正在验证更新…", UpdateState.READY_TO_INSTALL: "更新已验证",
            UpdateState.PREPARING_EXIT: "正在准备退出并更新…", UpdateState.FAILED: "更新操作失败",
            UpdateState.PREPARING_INSTALL: "正在复核更新包和更新组件…",
        }
        self.window.settings_page.set_update_state(labels.get(state, state.value), busy=state is UpdateState.CHECKING)
        self.window.set_update_busy(state in {UpdateState.DOWNLOADING, UpdateState.CANCELLING, UpdateState.VERIFYING, UpdateState.PREPARING_INSTALL, UpdateState.PREPARING_EXIT})
        if self._update_dialog is not None:
            self._update_dialog.set_state(state)

    def _update_available(self, manifest) -> None:
        self.window.show_update_available(str(manifest.version))
        self.window.settings_page.set_update_state(f"发现 {manifest.version}")

    def _show_update_dialog(self) -> None:
        manifest = self.updates.manifest
        if manifest is None:
            self.updates.check(manual=True)
            return
        if self._update_dialog is not None:
            self._update_dialog.raise_()
            self._update_dialog.activateWindow()
            return
        dialog = UpdateDialog(manifest, self.update_capability, self.window)
        dialog.download_requested.connect(self.updates.download)
        dialog.cancel_requested.connect(self.updates.cancel)
        dialog.install_requested.connect(self._request_update_install)
        dialog.release_page_requested.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        dialog.closed.connect(lambda: setattr(self, '_update_dialog', None))
        self._update_dialog = dialog
        dialog.show()

    def _update_progress(self, progress) -> None:
        if self._update_dialog is not None:
            self._update_dialog.set_progress(progress)

    def _update_ready(self, _package) -> None:
        self.window.hideUpdate()
        if self._update_dialog is not None:
            self._update_dialog.set_state(UpdateState.READY_TO_INSTALL)

    def _update_failed(self, error: AppError, manual: bool) -> None:
        logger.warning("Update operation failed: %s", error.technical_message)
        self.window.settings_page.set_update_state("检查或下载失败")
        if manual:
            self.show_error(error, title_text="更新失败", retry_callback=self._retry_update)

    def _retry_update(self) -> None:
        if self.updates.manifest is not None:
            self.updates.download()
        else:
            self.updates.check(manual=True)

    def _request_update_install(self) -> None:
        busy = self.queue.is_busy or self.metadata_process.is_running or bool(self._thumbnail_workers or self._settings_workers)
        if busy:
            self.window.dialogs.confirm(
                "任务仍在进行", "默认会继续当前任务。也可以明确取消任务、完成清理后退出并更新。",
                "取消任务并更新", self._update_install_answer, cancel="继续当前任务",
            )
            return
        self._launch_updater_and_exit()

    def _update_install_answer(self, accepted: bool) -> None:
        if not accepted:
            return
        self._update_install_pending = True
        self.queue.cancel_all()
        self.metadata_process.cancel()
        self._cancel_thumbnail()
        QTimer.singleShot(100, self._finish_update_install_when_idle)

    def _finish_update_install_when_idle(self) -> None:
        if not self._update_install_pending:
            return
        if self.queue.is_busy or self.metadata_process.is_running or self._thumbnail_workers or self._settings_workers:
            QTimer.singleShot(100, self._finish_update_install_when_idle)
            return
        self._update_install_pending = False
        self._launch_updater_and_exit()

    def _launch_updater_and_exit(self) -> None:
        if not self.updates.prepare_install(Path(sys.executable).parent, self.paths.data, os.getpid()):
            self.show_error(AppError('update_install_unavailable', '当前运行环境不支持自动安装，请从发布页面手动升级。', 'AUTO_INSTALL capability unavailable'))

    def _launch_prepared_updater(self, command) -> None:
        if self.queue.is_busy or self.metadata_process.is_running or self._thumbnail_workers or self._settings_workers:
            self.updates._set_state(UpdateState.READY_TO_INSTALL)
            self.show_error(AppError('update_tasks_started', '有新任务开始，请在任务结束后再次更新。', 'Tasks started during update preparation'))
            return
        try:
            subprocess.Popen(command, cwd=Path(command[0]).parent, close_fds=True, creationflags=0x08000000 if sys.platform == 'win32' else 0)
        except OSError as exc:
            self.updates._set_state(UpdateState.FAILED)
            self.show_error(AppError('updater_launch_failed', '无法启动更新程序，当前版本没有改变。', repr(exc)))
            return
        self.app.quit()

    def _apply_metadata_error(self, error: AppError) -> None:
        self._pending_retry = None
        self.show_error(error)

    def enqueue_download(self, video, option, filename: str, directory: str) -> None:
        try:
            output = Path(directory.strip())
            if not directory.strip():
                raise ValueError("下载目录不能为空。")
            stem = sanitize_filename(filename, directory=output, extension=f".{option.final_ext}")
            request = DownloadRequest(uuid.uuid4().hex, video, option, output, stem)
            created = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            record = HistoryRecord(
                request.task_id, video.video_id, video.url, video.title,
                output / f"{stem}.{option.final_ext}", option.label, None, None,
                TaskStatus.PENDING, created,
            )
            self.history.upsert(record)
            self._persisted_task_stages[request.task_id] = TaskStatus.PENDING
            self.refresh_history()
            self.queue.enqueue(request)
        except (OSError, ValueError) as exc:
            self.show_error(AppError(
                "invalid_output",
                str(exc),
                repr(exc),
                ErrorContext(url=video.url, selected_format=option.label, output_directory=directory, stage="Preparing download"),
            ))

    def _progress(self, progress) -> None:
        self.window.download_page.update_task(progress)
        if self._persisted_task_stages.get(progress.task_id) is progress.status:
            return
        self._persisted_task_stages[progress.task_id] = progress.status
        try:
            self.history.update_status(progress.task_id, progress.status)
        except Exception:
            logger.exception("Failed to persist task progress")

    def _cancelling(self, task_id: str) -> None:
        self.window.download_page.cancel_task(task_id)
        self._persisted_task_stages[task_id] = TaskStatus.CANCELLING
        try:
            self.history.update_status(task_id, TaskStatus.CANCELLING)
        except Exception:
            logger.exception("Failed to persist cancelling task")

    def _completed(self, result) -> None:
        getattr(self, "_persisted_task_stages", {}).pop(result.task_id, None)
        self.window.download_page.complete_task(result)
        try:
            self.history.update_status(
                result.task_id,
                TaskStatus.COMPLETED,
                file_path=result.file_path,
                file_size=result.file_size,
                completed_at=result.completed_at,
            )
        except Exception:
            logger.exception("Failed to persist completed task")
        self.refresh_history()
        if result.task_id in self._remove_intents:
            self._remove_intents.discard(result.task_id)
            self.window.download_page.remove_task(result.task_id)

    def _failed(self, task_id: str, error: AppError) -> None:
        getattr(self, "_persisted_task_stages", {}).pop(task_id, None)
        self.window.download_page.fail_task(task_id, TaskStatus.FAILED)
        try:
            self.history.update_status(task_id, TaskStatus.FAILED, error_summary=error.user_message)
        except Exception:
            logger.exception("Failed to persist failed task")
        self.refresh_history()
        if task_id in self._remove_intents:
            self._remove_intents.discard(task_id)
            self.window.download_page.remove_task(task_id)
        self.show_error(error)

    def _cancelled(self, task_id: str, cleanup_report) -> None:
        getattr(self, "_persisted_task_stages", {}).pop(task_id, None)
        self.window.download_page.fail_task(task_id, TaskStatus.CANCELLED, cleanup_report)
        summary = (
            "任务由用户取消，临时文件已清理。"
            if cleanup_report.succeeded
            else "任务由用户取消，但部分临时文件未能清理；可打开下载文件夹处理。"
        )
        try:
            self.history.update_status(task_id, TaskStatus.CANCELLED, error_summary=summary)
        except Exception:
            logger.exception("Failed to persist cancelled task")
        self.refresh_history()
        if task_id in self._remove_intents:
            self._remove_intents.discard(task_id)
            if cleanup_report.succeeded:
                self.window.download_page.remove_task(task_id)
            else:
                self._confirm_remove_after_incomplete_cleanup(
                    cleanup_report, lambda accepted: self.window.download_page.remove_task(task_id) if accepted else None,
                )

    def refresh_history(self) -> None:
        try:
            self.window.history_page.set_records(self.history.list_records())
        except Exception:
            logger.exception("Failed to load history")
            self.window.history_page.set_records([])

    def save_settings(self, settings) -> None:
        try:
            if settings.ffmpeg_directory:
                directory = Path(settings.ffmpeg_directory)
                if not (directory / "ffmpeg.exe").is_file() or not (directory / "ffprobe.exe").is_file():
                    raise ValueError("所选目录必须同时包含 ffmpeg.exe 和 ffprobe.exe。")
            self.settings_service.save(settings)
            self.network.configure(settings.proxy_mode, settings.custom_proxy_url)
            self.settings = settings
            self.theme.set_mode(settings.theme)
            self.window.settings_page.mark_saved(settings)
            self.window.download_page.set_default_directory(settings.download_directory)
            self.window.set_reduce_motion(settings.reduce_motion)
            self.ffmpeg = FfmpegService(configured_directory=settings.ffmpeg_directory or None)
            self.download_service.ffmpeg_path = self.ffmpeg.ffmpeg_path
            self.download_service.concurrent_fragments = settings.concurrent_fragments
            self.youtube.codec_preference = settings.codec_preference
        except (OSError, ValueError) as exc:
            logger.warning("Settings were not saved: %s", exc)
            self.window.settings_page.mark_save_failed(str(exc))

    def test_network_connection(self, mode: str, custom_proxy_url: str) -> None:
        try:
            policy = NetworkPolicy(mode, custom_proxy_url)
        except ValueError as exc:
            self.window.settings_page.set_network_test_result(False, str(exc))
            return
        worker = FunctionWorker(policy.test_connection)
        self._settings_workers.append(worker)
        worker.signals.result.connect(self._network_test_succeeded)
        worker.signals.error.connect(self._network_test_failed)
        worker.signals.finished.connect(lambda current=worker: self._settings_worker_finished(current))
        QThreadPool.globalInstance().start(worker)

    def _network_test_succeeded(self, result: NetworkTestResult) -> None:
        self.window.settings_page.set_network_test_result(
            True,
            f"连接成功（{result.elapsed_seconds:.2f} 秒） · {result.description}",
        )

    def _network_test_failed(self, error: AppError) -> None:
        logger.warning("Network connection test failed: %s", error.technical_message)
        self.window.settings_page.set_network_test_result(False, error.user_message)

    def _settings_worker_finished(self, worker: FunctionWorker) -> None:
        if worker in self._settings_workers:
            self._settings_workers.remove(worker)

    def copy_system_info(self) -> None:
        QGuiApplication.clipboard().setText(build_system_info(
            ffmpeg_path=self.ffmpeg.ffmpeg_path,
            deno_path=self.deno_path,
            data_path=self.paths.data,
        ))

    def _open_file(self, value: str) -> None:
        self._shell_action(lambda: open_path(value), "无法打开文件。")

    def _reveal_file(self, value: str) -> None:
        target = Path(value)
        action = (lambda: open_path(target)) if target.is_dir() else (lambda: reveal_in_folder(target))
        self._shell_action(action, "无法打开文件夹。")

    def _open_directory(self, value: Path) -> None:
        self._shell_action(lambda: open_path(value), "无法打开目录。")

    def _shell_action(self, action, message: str) -> None:
        try:
            action()
        except Exception as exc:
            self.show_error(AppError("shell_failed", message, repr(exc), ErrorContext(stage="Opening path")))

    def _change_thumbnail(self, record: HistoryRecord) -> None:
        dialog = ThumbnailDialog(record.file_path, record.video_id, self.paths.thumbnails, self.ffmpeg, self.window)
        dialog.error.connect(lambda error: self.show_error(error, title_text="封面处理失败"))
        dialog.thumbnail_set.connect(lambda result, task=record.task_id: self._thumbnail_saved(task, result))
        dialog.show()
        self._dialogs.append(dialog)
        dialog.closed.connect(lambda: self._dialogs.remove(dialog) if dialog in self._dialogs else None)

    def _retry_record(self, record: HistoryRecord) -> None:
        self._pending_retry = record
        self.window._select_page(0)
        self.window.download_page.set_url(record.url)
        self.fetch_metadata(record.url)

    def _retry_task(self, task_id: str) -> None:
        page = self.window.download_page
        if page.parse_state in {ParseState.RUNNING, ParseState.SLOW, ParseState.CANCELLING}:
            return
        request = page.task_request(task_id)
        if request is None or page.task_status(task_id) is not TaskStatus.FAILED:
            return
        # Retry is a new parse/selection, not an implicit download. Use the
        # retained request so deleting a history entry cannot break this action.
        self._pending_retry = request
        self.window._select_page(0)
        page.set_url(request.video.url)
        self.window.scroll_download_to_top()
        self.fetch_metadata(request.video.url)

    def _delete_history_record(self, record: HistoryRecord) -> None:
        if record.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return
        try:
            self.history.delete(record.task_id)
            self.refresh_history()
        except Exception as exc:
            self.show_error(AppError(
                "history_delete_failed",
                "无法删除这条历史记录；视频文件没有改变。",
                repr(exc),
            ))

    def _delete_history_records(self, task_ids: tuple[str, ...]) -> None:
        try:
            result = self.history.delete_many(task_ids)
            self.refresh_history()
            self.window.history_page.show_management_result(
                result.deleted_count, result.retained_count
            )
        except Exception as exc:
            self.show_error(AppError(
                "history_batch_delete_failed",
                "无法删除所选历史记录；视频文件没有改变。",
                repr(exc),
            ))

    def _clear_terminal_history(self) -> None:
        try:
            result = self.history.clear_terminal()
            self.refresh_history()
            self.window.history_page.show_management_result(
                result.deleted_count, result.retained_count
            )
        except Exception as exc:
            self.show_error(AppError(
                "history_clear_failed",
                "无法清空历史记录；视频文件没有改变。",
                repr(exc),
            ))

    def _remove_task_requested(self, task_id: str) -> None:
        position = self.queue.task_position(task_id)
        if position is None:
            self.window.download_page.remove_task(task_id)
            return
        request = self.window.download_page.task_request(task_id)
        if position == "active":
            self._confirm_cancel_and_remove(
                request.video.title if request else "当前任务",
                lambda accepted: self._cancel_and_remove_answer(task_id, accepted),
            )
            return
        self._cancel_and_remove_answer(task_id, True)

    def _cancel_and_remove_answer(self, task_id: str, accepted: bool) -> None:
        if not accepted:
            return
        self._remove_intents.add(task_id)
        if not self.queue.cancel(task_id):
            self._remove_intents.discard(task_id)

    def _confirm_cancel_and_remove(self, title: str, callback) -> None:
        self.window.dialogs.confirm(
            "取消并删除任务", f"取消下载并删除这张任务卡吗？\n{title}\n应用会先停止该任务、清理任务临时文件并保存取消状态；不会删除历史记录。",
            "取消并删除任务卡", callback,
        )

    def _confirm_remove_after_incomplete_cleanup(self, cleanup_report, callback) -> None:
        self.window.dialogs.confirm(
            "临时文件未完全清理", "文件可能仍被系统占用。你可以先打开文件夹处理，或确认后仍然移除任务卡。",
            "仍然移除", callback, folder_callback=lambda: self._reveal_file(cleanup_report.output_directory),
        )

    def _thumbnail_saved(self, task_id: str, result) -> None:
        try:
            record = self.history.get(task_id)
            previous = record.thumbnail_path if record else None
            if record:
                self.history.upsert(replace(record, file_path=result.file_path,
                                            file_size=result.file_path.stat().st_size, thumbnail_path=None))
            if previous and previous.is_file():
                try:
                    previous.resolve().relative_to(self.paths.thumbnails.resolve())
                except (OSError, ValueError):
                    pass
                else:
                    previous.unlink(missing_ok=True)
            self.refresh_history()
            self.window.history_page.invalidate_thumbnail(task_id)
        except Exception as exc:
            self.show_error(AppError("history_update_failed", "视频封面已写入，但历史记录更新失败。", repr(exc)))

    def show_error(self, error: AppError, *, title_text: str = "下载失败", retry_callback=None) -> None:
        logger.error("%s: %s", error.code, error.technical_message)
        report = build_error_report(
            error,
            app_version=__version__,
            yt_dlp_version=yt_dlp.version.__version__,
            ffmpeg_version=str(self.ffmpeg.ffmpeg_path or "Unavailable"),
        )
        dialog = ErrorDialog(error, report, self.window, title_text=title_text, retry_callback=retry_callback)
        dialog.show()
        self._dialogs.append(dialog)
        dialog.closed.connect(lambda: self._dialogs.remove(dialog) if dialog in self._dialogs else None)


def create_application(argv: list[str] | None = None) -> tuple[QApplication, AppController]:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv or sys.argv)
    app.setApplicationName("YT Downloader")
    app.setApplicationDisplayName("YT Downloader")
    app.setOrganizationName("YTDownloader")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(True)
    QLocale.setDefault(QLocale(QLocale.Language.Chinese, QLocale.Country.China))
    if not install_qt_zh_cn_translator(app):
        logger.warning("Qt Simplified Chinese translation resource is unavailable")
    font_families = resolve_font_families(system_default=app.font().family())
    app.setFont(application_font(font_families))
    install_typography_manager(app, font_families)
    paths = AppPaths.discover()
    paths.ensure()
    configure_logging(paths.logs)
    controller = AppController(app, paths)
    install_exception_hook(lambda exc, trace: QTimer.singleShot(0, lambda: controller.show_error(AppError(
        "unhandled_exception", "程序遇到了未处理的错误。", repr(exc), ErrorContext(traceback_text=trace, stage="GUI"),
    ))))
    return app, controller


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--smoke-test", action="store_true", help="start the packaged GUI briefly and exit")
    parser.add_argument("--self-test", action="store_true", help="run offline packaged resource and FFmpeg checks")
    parser.add_argument("--metadata-process-self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--update-health-check", nargs=2, metavar=("TRANSACTION_ID", "MARKER"), help=argparse.SUPPRESS)
    parser.add_argument("--render-preview", type=Path, help="save a window preview image and exit")
    parser.add_argument("--theme", choices=("system", "light", "dark"), help="temporary theme override for visual testing")
    parser.add_argument("--preview-page", choices=("download", "download-demo", "history", "settings", "about"), default="download")
    known, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    if known.self_test:
        paths = AppPaths.discover()
        paths.ensure()
        configure_logging(paths.logs)
        try:
            run_packaged_self_test(
                cache_directory=paths.cache,
                ffmpeg=FfmpegService(),
                deno_path=find_tool("deno"),
            )
            return 0
        except Exception:
            logger.exception("Packaged self-test failed")
            return 2
    app, controller = create_application([sys.argv[0], *qt_args])
    try:
        if known.metadata_process_self_test:
            return run_metadata_process_self_test(app)
        if known.theme:
            controller.theme.set_mode(known.theme)
        page_indexes = {"download": 0, "download-demo": 0, "history": 1, "settings": 2, "about": 3}
        controller.window._select_page(page_indexes[known.preview_page])
        if known.preview_page == "download-demo":
            option = FormatOption(
                "1080p", 1080, 30, "avc1.640028", "mp4a.40.2", "MP4", "mp4",
                "137+140", 1_374_000_000, True, "137", "140", True,
            )
            video = VideoInfo(
                "preview00001", "https://www.youtube.com/watch?v=preview00001", "Windows 11 Fluent Design：从构想到成品",
                "示例频道", 766, None, None, (option,),
            )
            controller.window.download_page.show_video(video)
            request = DownloadRequest("preview-task", video, option, Path(controller.settings.download_directory), video.title)
            controller.window.download_page.add_task(request)
            controller.window.download_page.update_task(DownloadProgress(
                request.task_id, TaskStatus.DOWNLOADING_VIDEO, 67, 920_000_000, 1_374_000_000, 8_700_000, 48,
            ))
        controller.window.show()
        if known.update_health_check:
            transaction_id, marker_value = known.update_health_check
            marker = Path(marker_value)
            def confirm_healthy_startup() -> None:
                if marker.name != 'startup-health.json' or not marker.parent.name.startswith('update-'):
                    logger.error('Rejected unsafe update health marker path')
                    app.quit()
                    return
                if marker.exists():
                    logger.error('Rejected pre-existing update health marker')
                    app.quit()
                    return
                marker.parent.mkdir(parents=True, exist_ok=True)
                temporary = marker.with_suffix('.tmp')
                temporary.write_text(json.dumps({
                    'status': 'ok', 'transaction_id': transaction_id, 'app_version': __version__,
                }), encoding='utf-8')
                temporary.replace(marker)
                if os.environ.get('YT_DOWNLOADER_UPDATE_HEALTH_SMOKE_EXIT') == '1':
                    QTimer.singleShot(0, app.quit)
            QTimer.singleShot(0, confirm_healthy_startup)
        elif known.render_preview:
            target = known.render_preview
            target.parent.mkdir(parents=True, exist_ok=True)
            QTimer.singleShot(600, lambda: (controller.window.grab().save(str(target)), app.quit()))
        elif known.smoke_test:
            QTimer.singleShot(800, app.quit)
        return app.exec()
    finally:
        controller.window.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

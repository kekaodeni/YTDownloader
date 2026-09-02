"""Application composition root. Services and Qt pages meet only here."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import threading
import uuid

from PySide6.QtCore import QLocale, QThreadPool, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox
import yt_dlp.version

from yt_downloader import __version__
from yt_downloader.core.errors import AppError, ErrorContext
from yt_downloader.core.filename import sanitize_filename
from yt_downloader.core.models import DownloadProgress, DownloadRequest, FormatOption, HistoryRecord, TaskStatus, VideoInfo
from yt_downloader.infrastructure.logging_config import configure_logging, install_exception_hook
from yt_downloader.infrastructure.paths import AppPaths, default_videos_directory
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.infrastructure.shell import open_path, reveal_in_folder
from yt_downloader.infrastructure.system_info import build_system_info
from yt_downloader.infrastructure.self_test import run_packaged_self_test
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.error_report_service import build_error_report
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.history_service import HistoryRepository
from yt_downloader.services.network_policy import NetworkPolicy, NetworkTestResult
from yt_downloader.services.settings_service import SettingsService
from yt_downloader.services.youtube_service import YoutubeService
from yt_downloader.ui.main_window import MainWindow
from yt_downloader.ui.theme import ThemeManager
from yt_downloader.ui.typography import application_font, resolve_font_families
from yt_downloader.ui.widgets.error_dialog import ErrorDialog
from yt_downloader.ui.widgets.thumbnail_dialog import ThumbnailDialog
from yt_downloader.workers.download_queue import DownloadQueueController
from yt_downloader.workers.function_worker import FunctionWorker
from yt_downloader.workers.request_gate import LatestRequestGate, RequestToken


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
        self.youtube = YoutubeService(deno_path=self.deno_path, network_policy=self.network)
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
        )
        self.queue = DownloadQueueController(self.download_service, self.window)
        self._metadata_cancel: threading.Event | None = None
        self._metadata_workers: list[FunctionWorker] = []
        self._settings_workers: list[FunctionWorker] = []
        self._metadata_gate: LatestRequestGate[object] = LatestRequestGate()
        self._pending_retry: HistoryRecord | None = None
        self._dialogs: list[object] = []
        self._wire()
        self.refresh_history()
        clipboard = QGuiApplication.clipboard().text().strip()
        if clipboard:
            self.window.download_page.set_clipboard_hint(clipboard)

    def _wire(self) -> None:
        download = self.window.download_page
        download.parse_requested.connect(self.fetch_metadata)
        download.download_requested.connect(self.enqueue_download)
        download.cancel_requested.connect(self.queue.cancel)
        download.open_file_requested.connect(self._open_file)
        download.open_folder_requested.connect(self._reveal_file)
        history = self.window.history_page
        history.open_file_requested.connect(self._open_file)
        history.open_folder_requested.connect(self._reveal_file)
        history.copy_link_requested.connect(lambda value: QGuiApplication.clipboard().setText(value))
        history.thumbnail_requested.connect(self._change_thumbnail)
        history.retry_requested.connect(self._retry_record)
        history.delete_requested.connect(self._delete_history_record)
        settings = self.window.settings_page
        settings.save_requested.connect(self.save_settings)
        settings.network_test_requested.connect(self.test_network_connection)
        settings.theme_preview_requested.connect(self.theme.set_mode)
        self.theme.theme_changed.connect(self.window.apply_theme)
        settings.open_logs_requested.connect(lambda: self._open_directory(self.paths.logs))
        settings.copy_system_info_requested.connect(self.copy_system_info)
        self.queue.task_queued.connect(download.add_task)
        self.queue.task_started.connect(download.task_started)
        self.queue.cancelling.connect(self._cancelling)
        self.queue.progress.connect(self._progress)
        self.queue.completed.connect(self._completed)
        self.queue.failed.connect(self._failed)
        self.queue.cancelled.connect(self._cancelled)
        self.queue.busy_changed.connect(self.window.set_download_busy)
        self.window.cancel_all_requested.connect(self.queue.cancel_all)

    def fetch_metadata(self, url: str) -> None:
        if self._metadata_cancel:
            self._metadata_cancel.set()
        token = self._metadata_gate.begin(url.strip())
        cancel = threading.Event()
        self._metadata_cancel = cancel
        self.window.download_page.set_loading(True)
        worker = FunctionWorker(self.youtube.fetch_metadata, url, cancel)
        self._metadata_workers.append(worker)
        worker.signals.result.connect(lambda video, current=token: self._metadata_result(current, video))
        worker.signals.error.connect(lambda error, current=token: self._metadata_error(current, error))
        worker.signals.finished.connect(lambda w=worker, current=token: self._metadata_finished(w, cancel, current))
        QThreadPool.globalInstance().start(worker)

    def _metadata_finished(self, worker: FunctionWorker, cancel: threading.Event, token: RequestToken) -> None:
        if worker in self._metadata_workers:
            self._metadata_workers.remove(worker)
        if self._metadata_cancel is cancel and self._metadata_gate.finish(token):
            self._metadata_cancel = None
            self.window.download_page.set_loading(False)

    def _metadata_result(self, token: RequestToken, video) -> None:
        self._metadata_gate.deliver(token, self._apply_metadata_result, video)

    def _apply_metadata_result(self, video) -> None:
        retry = self._pending_retry
        preferred = retry.quality_label if retry else self.settings.default_quality
        self.window.download_page.show_video(video, preferred_quality=preferred)
        if retry:
            self._pending_retry = None
            option = next((item for item in video.formats if item.label == retry.quality_label), None)
            option = option or next((item for item in video.formats if item.is_recommended), video.formats[0])
            self.enqueue_download(video, option, retry.file_path.stem or video.title, str(retry.file_path.parent))

    def _metadata_error(self, token: RequestToken, error: AppError) -> None:
        self._metadata_gate.deliver(token, self._apply_metadata_error, error)

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
        try:
            self.history.update_status(progress.task_id, progress.status)
        except Exception:
            logger.exception("Failed to persist task progress")

    def _cancelling(self, task_id: str) -> None:
        self.window.download_page.cancel_task(task_id)
        try:
            self.history.update_status(task_id, TaskStatus.CANCELLING)
        except Exception:
            logger.exception("Failed to persist cancelling task")

    def _completed(self, result) -> None:
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

    def _failed(self, task_id: str, error: AppError) -> None:
        self.window.download_page.fail_task(task_id, TaskStatus.FAILED)
        try:
            self.history.update_status(task_id, TaskStatus.FAILED, error_summary=error.user_message)
        except Exception:
            logger.exception("Failed to persist failed task")
        self.refresh_history()
        self.show_error(error)

    def _cancelled(self, task_id: str) -> None:
        self.window.download_page.fail_task(task_id, TaskStatus.CANCELLED)
        try:
            self.history.update_status(task_id, TaskStatus.CANCELLED, error_summary="任务由用户取消；可重试并续传 .part 文件。")
        except Exception:
            logger.exception("Failed to persist cancelled task")
        self.refresh_history()

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
        self._shell_action(lambda: reveal_in_folder(value), "无法在文件夹中显示该文件。")

    def _open_directory(self, value: Path) -> None:
        self._shell_action(lambda: open_path(value), "无法打开目录。")

    def _shell_action(self, action, message: str) -> None:
        try:
            action()
        except Exception as exc:
            self.show_error(AppError("shell_failed", message, repr(exc), ErrorContext(stage="Opening path")))

    def _change_thumbnail(self, record: HistoryRecord) -> None:
        dialog = ThumbnailDialog(record.file_path, record.video_id, self.paths.thumbnails, self.ffmpeg, self.window)
        dialog.error.connect(self.show_error)
        dialog.thumbnail_set.connect(lambda result, task=record.task_id: self._thumbnail_saved(task, result))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        self._dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self._dialogs.remove(dialog) if dialog in self._dialogs else None)

    def _retry_record(self, record: HistoryRecord) -> None:
        self._pending_retry = record
        self.window._select_page(0)
        self.window.download_page.url_input.setText(record.url)
        self.fetch_metadata(record.url)

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

    def _thumbnail_saved(self, task_id: str, _result) -> None:
        try:
            record = self.history.get(task_id)
            previous = record.thumbnail_path if record else None
            self.history.update_thumbnail(task_id, None)
            if previous and previous.is_file():
                try:
                    previous.resolve().relative_to(self.paths.thumbnails.resolve())
                except (OSError, ValueError):
                    pass
                else:
                    previous.unlink(missing_ok=True)
            self.refresh_history()
        except Exception as exc:
            self.show_error(AppError("history_update_failed", "视频封面已写入，但历史记录更新失败。", repr(exc)))

    def show_error(self, error: AppError) -> None:
        logger.error("%s: %s", error.code, error.technical_message)
        report = build_error_report(
            error,
            app_version=__version__,
            yt_dlp_version=yt_dlp.version.__version__,
            ffmpeg_version=str(self.ffmpeg.ffmpeg_path or "Unavailable"),
        )
        dialog = ErrorDialog(error, report, self.window)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        self._dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self._dialogs.remove(dialog) if dialog in self._dialogs else None)


def create_application(argv: list[str] | None = None) -> tuple[QApplication, AppController]:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv or sys.argv)
    app.setApplicationName("YT Downloader")
    app.setApplicationDisplayName("YT Downloader")
    app.setOrganizationName("YTDownloader")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(True)
    app.setFont(application_font(resolve_font_families(system_default=app.font().family())))
    QLocale.setDefault(QLocale(QLocale.Language.Chinese, QLocale.Country.China))
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
    parser.add_argument("--render-preview", type=Path, help="save a window preview image and exit")
    parser.add_argument("--theme", choices=("system", "light", "dark"), help="temporary theme override for visual testing")
    parser.add_argument("--preview-page", choices=("download", "download-demo", "history", "settings", "about"), default="download")
    known, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    app, controller = create_application([sys.argv[0], *qt_args])
    if known.self_test:
        try:
            run_packaged_self_test(
                cache_directory=controller.paths.cache,
                ffmpeg=controller.ffmpeg,
                deno_path=controller.deno_path,
            )
            return 0
        except Exception:
            logger.exception("Packaged self-test failed")
            return 2
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
    if known.render_preview:
        target = known.render_preview
        target.parent.mkdir(parents=True, exist_ok=True)
        QTimer.singleShot(600, lambda: (controller.window.grab().save(str(target)), app.quit()))
    elif known.smoke_test:
        QTimer.singleShot(800, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

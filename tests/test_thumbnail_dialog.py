from pathlib import Path
import threading
import time

from PIL import Image
from PySide6.QtCore import Qt

from yt_downloader.services.ffmpeg_service import CoverEmbedResult, ExplorerCoverStatus
from yt_downloader.core.errors import ErrorContext, OperationCancelled
from yt_downloader.ui.quick_cover import CoverSession as ThumbnailDialog


class _FakeCoverService:
    def probe_duration(self, _media: Path, **_kwargs) -> float:
        return 2.0

    def extract_frame(self, _media: Path, _timestamp: float, output: Path, **_kwargs) -> Path:
        Image.new("RGB", (160, 90), "#1267B0").save(output, "JPEG")
        return output

    def embed_cover(self, media: Path, cover: Path, **_kwargs) -> CoverEmbedResult:
        assert cover.is_file()
        return CoverEmbedResult(
            media,
            True,
            ExplorerCoverStatus.NOT_USED,
            "封面已写入视频，但当前容器或系统的 Explorer 没有采用该封面。",
        )


class _SlowPreviewService(_FakeCoverService):
    def __init__(self) -> None:
        self.started = threading.Event()

    def extract_frame(self, _media: Path, _timestamp: float, output: Path, **kwargs) -> Path:
        self.started.set()
        cancel_event = kwargs["cancel_event"]
        while not cancel_event.is_set():
            time.sleep(0.01)
        raise OperationCancelled(ErrorContext(stage="Extracting thumbnail"))


def test_dialog_uses_temporary_preview_and_reports_explorer_result_inline(qtbot, quick_window, tmp_path: Path) -> None:
    media = tmp_path / "视频.mp4"
    media.write_bytes(b"test-media")
    previews = tmp_path / "preview-cache"
    dialog = ThumbnailDialog(media, "video-id", previews, _FakeCoverService(), quick_window)  # type: ignore[arg-type]
    dialog.show()
    qtbot.waitUntil(lambda: dialog.state["previewEnabled"], timeout=1000)

    dialog.generatePreview()
    qtbot.waitUntil(lambda: dialog.state["applyEnabled"], timeout=1000)
    assert list(previews.glob("*.jpg"))

    with qtbot.waitSignal(dialog.thumbnail_set, timeout=1000):
        dialog.apply()

    assert "封面已写入视频" in dialog.state["message"]
    assert "Explorer 没有采用" in dialog.state["message"]
    assert not list(previews.glob("*.jpg"))


def test_closing_during_preview_waits_for_worker_then_leaves_no_jpeg(qtbot, quick_window, tmp_path: Path) -> None:
    media = tmp_path / "视频.mp4"
    media.write_bytes(b"test-media")
    previews = tmp_path / "preview-cache"
    service = _SlowPreviewService()
    dialog = ThumbnailDialog(media, "video-id", previews, service, quick_window)  # type: ignore[arg-type]
    dialog.show()
    qtbot.waitUntil(lambda: dialog.state["previewEnabled"], timeout=1000)
    dialog.generatePreview()
    assert service.started.wait(1)

    dialog.reject()

    assert dialog.state["open"]
    qtbot.waitUntil(lambda: not dialog.state["open"], timeout=1000)
    assert not list(previews.glob("*.jpg"))


def test_cover_preview_preserves_full_portrait_and_landscape_shape(qtbot, quick_window, tmp_path, qapp):
    from conftest import run_frames, find_item
    media=tmp_path/'video.mp4';media.write_bytes(b'test')
    dialog=ThumbnailDialog(media,'aspect',tmp_path/'previews',_FakeCoverService(),quick_window)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.state['previewEnabled'])
    for width,height in ((180,320),(320,180),(240,240)):
        Image.new('RGB',(width,height),'#1267B0').save(dialog.preview_path,'JPEG')
        dialog._preview_ready(dialog.preview_path)
        run_frames(qapp,350)
        preview=find_item(quick_window,'coverPreview')
        assert abs(preview.width()/preview.height()-width/height)<0.001
        assert preview.property('imageFillMode')==1  # Image.PreserveAspectFit
        assert abs(dialog.state['previewRatio']-width/height)<0.001
    dialog.reject()


def test_webm_cover_copy_updates_real_history_and_keeps_original(qtbot, quick_window, tmp_path):
    import hashlib
    from types import SimpleNamespace
    from yt_downloader.app import AppController
    from yt_downloader.core.models import HistoryRecord, TaskStatus
    from yt_downloader.services.ffmpeg_service import FfmpegService
    from yt_downloader.services.history_service import HistoryRepository
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QImage
    service = FfmpegService(shell_thumbnail_checker=lambda *_: None)
    assert service.available
    media = tmp_path / "真实竖屏.webm"
    service._run([str(service.ffmpeg_path), "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=90x160:d=1:r=15",
                  "-f", "lavfi", "-i", "sine=duration=1", "-shortest", "-c:v", "libvpx-vp9", "-c:a", "libopus", "-y", str(media)])
    original = hashlib.sha256(media.read_bytes()).hexdigest()
    occupied = media.with_name(media.stem + " (封面).mkv")
    occupied.write_bytes(b"existing file must stay")
    history = HistoryRepository(tmp_path / "history.db")
    record = HistoryRecord("webm", "video", "https://example.invalid", "竖屏", media, "720p", media.stat().st_size, None, TaskStatus.COMPLETED, "now")
    history.upsert(record)
    page = quick_window.history_page
    page.configure_thumbnails(service, tmp_path / "history-cache")
    page.set_records(history.list_records()); page.select(record.task_id)
    errors = []
    controller = SimpleNamespace(history=history, window=quick_window, paths=SimpleNamespace(thumbnails=tmp_path / "previews"),
                                 refresh_history=lambda: page.set_records(history.list_records()), show_error=errors.append)
    dialog = ThumbnailDialog(media, "webm", tmp_path / "previews", service, quick_window)
    results = []
    dialog.error.connect(errors.append)
    dialog.thumbnail_set.connect(lambda result: (results.append(result), AppController._thumbnail_saved(controller, record.task_id, result)))
    dialog.show()
    assert dialog.state["applyText"] == "另存为 MKV 并写入封面"
    assert "保留原文件" in dialog.state["message"]
    qtbot.waitUntil(lambda: dialog.state["previewEnabled"], timeout=5000)
    dialog.generatePreview()
    qtbot.waitUntil(lambda: dialog.state["applyEnabled"], timeout=5000)
    dialog.apply(); dialog.apply()
    qtbot.waitUntil(lambda: dialog.state["completed"] or bool(errors), timeout=10000)
    assert not errors
    assert len(results) == 1
    saved = history.get(record.task_id)
    assert saved.file_path.name == media.stem + " (封面 2).mkv"
    assert saved.file_size == saved.file_path.stat().st_size
    assert page.selected_record().file_path == saved.file_path
    assert page.state["selectedId"] == record.task_id
    qtbot.waitUntil(lambda: bool(page.model.get(0)["thumbnail"]), timeout=5000)
    assert QImage(QUrl(page.model.get(0)["thumbnail"]).toLocalFile()).pixelColor(20, 20).red() > 200
    assert hashlib.sha256(media.read_bytes()).hexdigest() == original
    assert occupied.read_bytes() == b"existing file must stay"
    assert not list((tmp_path / "previews").glob("*.jpg"))
    dialog.reject()

from pathlib import Path
import threading
import time

from PIL import Image
from PySide6.QtCore import Qt

from yt_downloader.services.ffmpeg_service import CoverEmbedResult, ExplorerCoverStatus
from yt_downloader.core.errors import ErrorContext, OperationCancelled
from yt_downloader.ui.widgets.thumbnail_dialog import ThumbnailDialog


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


def test_dialog_uses_temporary_preview_and_reports_explorer_result_inline(qtbot, tmp_path: Path) -> None:
    media = tmp_path / "视频.mp4"
    media.write_bytes(b"test-media")
    previews = tmp_path / "preview-cache"
    dialog = ThumbnailDialog(media, "video-id", previews, _FakeCoverService())  # type: ignore[arg-type]
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.preview_button.isEnabled, timeout=1000)

    qtbot.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(dialog.apply_button.isEnabled, timeout=1000)
    assert list(previews.glob("*.jpg"))

    with qtbot.waitSignal(dialog.thumbnail_set, timeout=1000):
        qtbot.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)

    assert "封面已写入视频" in dialog.result_label.text()
    assert "Explorer 没有采用" in dialog.result_label.text()
    assert not list(previews.glob("*.jpg"))


def test_closing_during_preview_waits_for_worker_then_leaves_no_jpeg(qtbot, tmp_path: Path) -> None:
    media = tmp_path / "视频.mp4"
    media.write_bytes(b"test-media")
    previews = tmp_path / "preview-cache"
    service = _SlowPreviewService()
    dialog = ThumbnailDialog(media, "video-id", previews, service)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.preview_button.isEnabled, timeout=1000)
    qtbot.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
    assert service.started.wait(1)

    dialog.reject()

    assert dialog.isVisible()
    qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=1000)
    assert not list(previews.glob("*.jpg"))

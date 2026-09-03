from pathlib import Path
from types import SimpleNamespace

from test_download_service import _request
from test_history_repository import _record
from yt_downloader.app import AppController
from yt_downloader.core.models import TaskStatus


def test_history_retry_reparses_and_prefills_options_without_auto_downloading(tmp_path: Path) -> None:
    controller = AppController.__new__(AppController)
    retry = _record(tmp_path, "retry", TaskStatus.FAILED)
    retry = retry.__class__(
        **{
            field: getattr(retry, field)
            for field in retry.__dataclass_fields__
            if field != "file_path"
        },
        file_path=tmp_path / "历史文件名.mp4",
    )
    controller._pending_retry = retry
    controller.settings = SimpleNamespace(default_quality="recommended")
    calls: list[tuple] = []
    controller.window = SimpleNamespace(download_page=SimpleNamespace(
        show_video=lambda video, **kwargs: calls.append(("show", video.video_id, kwargs)),
        set_retry_defaults=lambda filename, directory: calls.append(("defaults", filename, directory)),
    ))
    controller.enqueue_download = lambda *_args: calls.append(("unexpected-download",))

    controller._apply_metadata_result(_request(tmp_path).video)

    assert calls == [
        ("show", "dQw4w9WgXcQ", {"preferred_quality": "1080p"}),
        ("defaults", "历史文件名", str(tmp_path)),
    ]
    assert controller._pending_retry is None

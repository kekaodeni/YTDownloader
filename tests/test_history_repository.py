from pathlib import Path

from yt_downloader.core.models import HistoryRecord, TaskStatus
from yt_downloader.services.history_service import HistoryRepository


def _record(tmp_path: Path, task_id: str, status: TaskStatus) -> HistoryRecord:
    return HistoryRecord(
        task_id=task_id,
        video_id="dQw4w9WgXcQ",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="中文标题 😀",
        file_path=tmp_path / "中文标题.mp4",
        quality_label="1080p",
        file_size=123,
        thumbnail_path=tmp_path / "thumb.jpg",
        status=status,
        created_at="2026-09-01T19:20:31+08:00",
    )


def test_persists_and_recovers_interrupted_tasks(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    repository.upsert(_record(tmp_path, "active", TaskStatus.DOWNLOADING_VIDEO))
    repository.upsert(_record(tmp_path, "done", TaskStatus.COMPLETED))

    assert {item.task_id for item in repository.list_records()} == {"active", "done"}
    assert repository.mark_interrupted() == 1
    active = repository.get("active")
    assert active is not None
    assert active.status == TaskStatus.CANCELLED
    assert active.error_summary == "上次运行中断"
    assert repository.get("done").status == TaskStatus.COMPLETED  # type: ignore[union-attr]

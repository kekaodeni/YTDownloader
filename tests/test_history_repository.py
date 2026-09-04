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


def test_thumbnail_reference_can_be_cleared_after_embedding_into_video(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    repository.upsert(_record(tmp_path, "embedded", TaskStatus.COMPLETED))

    repository.update_thumbnail("embedded", None)

    assert repository.get("embedded").thumbnail_path is None  # type: ignore[union-attr]


def test_delete_removes_only_history_row_and_never_the_video_file(tmp_path: Path) -> None:
    video = tmp_path / "中文标题.mp4"
    video.write_bytes(b"keep-video")
    repository = HistoryRepository(tmp_path / "history.db")
    repository.upsert(_record(tmp_path, "delete-me", TaskStatus.COMPLETED))

    assert repository.delete("delete-me")

    assert repository.get("delete-me") is None
    assert video.read_bytes() == b"keep-video"


def test_delete_many_is_transactional_and_preserves_active_rows_and_files(tmp_path: Path) -> None:
    video = tmp_path / "中文标题.mp4"
    video.write_bytes(b"keep-video")
    repository = HistoryRepository(tmp_path / "history.db")
    repository.upsert(_record(tmp_path, "done", TaskStatus.COMPLETED))
    repository.upsert(_record(tmp_path, "failed", TaskStatus.FAILED))
    repository.upsert(_record(tmp_path, "active", TaskStatus.DOWNLOADING_VIDEO))

    result = repository.delete_many(("done", "failed", "active"))

    assert result.deleted_count == 2
    assert result.retained_count == 1
    assert repository.get("done") is None
    assert repository.get("failed") is None
    assert repository.get("active") is not None
    assert video.read_bytes() == b"keep-video"


def test_clear_terminal_preserves_non_terminal_rows(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    repository.upsert(_record(tmp_path, "done", TaskStatus.COMPLETED))
    repository.upsert(_record(tmp_path, "cancelled", TaskStatus.CANCELLED))
    repository.upsert(_record(tmp_path, "queued", TaskStatus.PENDING))

    result = repository.clear_terminal()

    assert result.deleted_count == 2
    assert result.retained_count == 1
    assert [record.task_id for record in repository.list_records()] == ["queued"]

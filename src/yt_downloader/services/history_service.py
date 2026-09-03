"""SQLite-backed history for tasks created by this application only."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

from yt_downloader.core.models import HistoryRecord, TaskStatus


class HistoryRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connection() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version == 0:
                connection.executescript("""
                    CREATE TABLE downloads (
                        task_id TEXT PRIMARY KEY,
                        video_id TEXT NOT NULL,
                        url TEXT NOT NULL,
                        title TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        quality_label TEXT NOT NULL,
                        file_size INTEGER,
                        thumbnail_path TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        completed_at TEXT,
                        error_summary TEXT
                    );
                    CREATE INDEX idx_downloads_created_at ON downloads(created_at DESC);
                    PRAGMA user_version=1;
                """)
                version = 1
            if version != 1:
                raise RuntimeError(f"Unsupported history database version: {version}")

    def upsert(self, record: HistoryRecord) -> None:
        with self._connection() as connection:
            connection.execute("""
                INSERT INTO downloads (
                    task_id, video_id, url, title, file_path, quality_label,
                    file_size, thumbnail_path, status, created_at, completed_at, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    video_id=excluded.video_id,
                    url=excluded.url,
                    title=excluded.title,
                    file_path=excluded.file_path,
                    quality_label=excluded.quality_label,
                    file_size=excluded.file_size,
                    thumbnail_path=excluded.thumbnail_path,
                    status=excluded.status,
                    completed_at=excluded.completed_at,
                    error_summary=excluded.error_summary
            """, (
                record.task_id, record.video_id, record.url, record.title,
                str(record.file_path), record.quality_label, record.file_size,
                str(record.thumbnail_path) if record.thumbnail_path else None,
                record.status.value, record.created_at, record.completed_at,
                record.error_summary,
            ))

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        file_path: str | Path | None = None,
        file_size: int | None = None,
        completed_at: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        fields = ["status=?", "completed_at=?", "error_summary=?"]
        values: list[object] = [status.value, completed_at, error_summary]
        if file_path is not None:
            fields.append("file_path=?")
            values.append(str(file_path))
        if file_size is not None:
            fields.append("file_size=?")
            values.append(file_size)
        values.append(task_id)
        with self._connection() as connection:
            connection.execute(f"UPDATE downloads SET {', '.join(fields)} WHERE task_id=?", values)

    def update_thumbnail(self, task_id: str, thumbnail_path: str | Path | None) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE downloads SET thumbnail_path=? WHERE task_id=?",
                (str(thumbnail_path) if thumbnail_path else None, task_id),
            )

    def mark_interrupted(self) -> int:
        terminal = (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value)
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE downloads SET status=?, error_summary=? WHERE status NOT IN (?, ?, ?)",
                (TaskStatus.CANCELLED.value, "上次运行中断", *terminal),
            )
            return int(cursor.rowcount)

    def get(self, task_id: str) -> HistoryRecord | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM downloads WHERE task_id=?", (task_id,)).fetchone()
        return self._from_row(row) if row else None

    def delete(self, task_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM downloads WHERE task_id=?", (task_id,))
            return cursor.rowcount > 0

    def list_records(self, *, limit: int = 500) -> list[HistoryRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM downloads ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(
            task_id=row["task_id"],
            video_id=row["video_id"],
            url=row["url"],
            title=row["title"],
            file_path=Path(row["file_path"]),
            quality_label=row["quality_label"],
            file_size=row["file_size"],
            thumbnail_path=Path(row["thumbnail_path"]) if row["thumbnail_path"] else None,
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            error_summary=row["error_summary"],
        )

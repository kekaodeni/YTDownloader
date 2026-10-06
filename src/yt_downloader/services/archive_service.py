"""Persistent successful-media archive, independent of visible History rows."""
from contextlib import contextmanager
from dataclasses import dataclass, fields
import json
from pathlib import Path
import sqlite3
import stat

from yt_downloader.core.models import TaskStatus
from yt_downloader.services.error_report_service import redact_sensitive


def canonical_identity(extractor_key, media_id, content_kind='video'):
    key = str(extractor_key or '').strip().casefold()
    return key, str(media_id or '').strip(), 'audio' if content_kind == 'audio' else 'video'


@dataclass(frozen=True, slots=True)
class ArchiveRecord:
    extractor_key: str
    media_id: str
    content_kind: str
    title: str
    source_url: str
    quality_label: str
    format_id: str
    container: str
    downloaded_at: str
    output_path: str
    file_size: int | None
    playlist_id: str = ''

    @property
    def file_exists(self):
        # The recorded final path is authoritative. Missing/inaccessible/empty
        # outputs leave the success record intact, but cannot block a download.
        try:
            output = Path(self.output_path).stat()
            return stat.S_ISREG(output.st_mode) and output.st_size > 0
        except (OSError, ValueError):
            return False


class ArchiveRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='download_archive'").fetchone()
            if not exists:
                # Snapshot an existing v0.6 History database without removing it.
                if connection.execute("SELECT 1 FROM sqlite_master WHERE name='downloads'").fetchone():
                    backup = self.database_path.with_suffix(self.database_path.suffix + '.pre-archive.bak')
                    if not backup.exists():
                        with sqlite3.connect(backup) as destination:
                            connection.backup(destination)
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('''CREATE TABLE download_archive (
                    extractor_key TEXT NOT NULL, media_id TEXT NOT NULL,
                    content_kind TEXT NOT NULL CHECK(content_kind IN ('video', 'audio')),
                    title TEXT NOT NULL, source_url TEXT NOT NULL, quality_label TEXT NOT NULL,
                    format_id TEXT NOT NULL, container TEXT NOT NULL, downloaded_at TEXT NOT NULL,
                    output_path TEXT NOT NULL, file_size INTEGER, playlist_id TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(extractor_key, media_id, content_kind))''')
                connection.execute('CREATE TABLE archive_schema (revision INTEGER NOT NULL)')
                connection.execute('INSERT INTO archive_schema VALUES (1)')
            revision = connection.execute('SELECT revision FROM archive_schema').fetchone()[0]
            if revision != 1:
                raise RuntimeError(f'Unsupported archive schema: {revision}')
        # Legacy History has no reliable clip/full marker. Do not backfill it:
        # a prior short section must never block a future full-video download.

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA busy_timeout=10000')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_download(self, request, result, status=TaskStatus.COMPLETED):
        media = result.resolved_media or request.video
        option = result.resolved_format or request.format
        identity = canonical_identity(media.extractor_key or media.extractor, media.video_id,
                                      'audio' if request.media_mode == 'audio_only' else 'video')
        if (status != TaskStatus.COMPLETED or request.clip_enabled or media.is_collection
                or not all(identity) or not result.file_path.is_file()):
            return False
        record = ArchiveRecord(*identity, media.title, redact_sensitive(media.original_url or media.url),
                               option.label, option.format_selector, result.file_path.suffix.lstrip('.'),
                               result.completed_at, str(result.file_path), result.file_size,
                               request.playlist_id)
        values = tuple(getattr(record, field.name) for field in fields(record))
        with self._connection() as connection:
            connection.execute('''INSERT INTO download_archive VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(extractor_key, media_id, content_kind) DO UPDATE SET
                title=excluded.title, source_url=excluded.source_url, quality_label=excluded.quality_label,
                format_id=excluded.format_id, container=excluded.container, downloaded_at=excluded.downloaded_at,
                output_path=excluded.output_path, file_size=excluded.file_size, playlist_id=excluded.playlist_id''', values)
        return True

    def lookup_many(self, identities):
        identities = list(dict.fromkeys(canonical_identity(*identity) for identity in identities))
        if not identities:
            return {}
        with self._connection() as connection:
            rows = connection.execute('''WITH requested AS (
                SELECT json_extract(value, '$[0]') AS extractor_key,
                       json_extract(value, '$[1]') AS media_id,
                       json_extract(value, '$[2]') AS content_kind FROM json_each(?))
                SELECT a.* FROM download_archive a JOIN requested r
                USING(extractor_key, media_id, content_kind)''', (json.dumps(identities),)).fetchall()
        return {canonical_identity(row['extractor_key'], row['media_id'], row['content_kind']):
                ArchiveRecord(**dict(row)) for row in rows}

    def lookup(self, extractor_key, media_id, content_kind='video'):
        identity = canonical_identity(extractor_key, media_id, content_kind)
        return self.lookup_many([identity]).get(identity)

    def lookup_active_many(self, identities):
        """One SQL batch, then one cheap stat per matching recorded output."""
        return {identity: record for identity, record in self.lookup_many(identities).items()
                if record.file_exists}

    def lookup_active(self, extractor_key, media_id, content_kind='video'):
        identity = canonical_identity(extractor_key, media_id, content_kind)
        return self.lookup_active_many([identity]).get(identity)

    def count(self):
        with self._connection() as connection:
            return connection.execute('SELECT COUNT(*) FROM download_archive').fetchone()[0]

    def clear(self):
        with self._connection() as connection:
            connection.execute('DELETE FROM download_archive')

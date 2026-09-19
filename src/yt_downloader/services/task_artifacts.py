"""Task-scoped download workspace ownership and bounded cleanup."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import logging
import os
from pathlib import Path
import shutil
import stat
import time
import threading
from typing import Callable

from yt_downloader.core.errors import CancellationCleanupReport
from yt_downloader.core.filename import ensure_unique_path


logger = logging.getLogger(__name__)
_COMMIT_LOCK = threading.Lock()


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return path.is_symlink()
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


@dataclass(slots=True)
class TaskArtifactRegistry:
    output_directory: Path
    task_id: str
    sleeper: Callable[[float], None] = time.sleep
    temporary_root: Path = field(init=False)
    workspace: Path = field(init=False)

    def __post_init__(self) -> None:
        self.output_directory = self.output_directory.resolve()
        token = hashlib.sha256(self.task_id.encode("utf-8")).hexdigest()[:16]
        self.temporary_root = self.output_directory / ".ytdownloader-tmp"
        self.workspace = self.temporary_root / f"task-{token}"

    def prepare(self) -> None:
        self.temporary_root.mkdir(parents=True, exist_ok=True)
        resolved_root = self.temporary_root.resolve()
        if resolved_root.parent != self.output_directory or _is_reparse_point(self.temporary_root):
            raise OSError("Task temporary root is outside the selected output directory")
        self.workspace.mkdir()

    def download_path(self, extension: str) -> Path:
        return self.workspace / f"download.{extension}"

    @property
    def output_template(self) -> str:
        return str(self.workspace / "download.%(ext)s")

    def find_completed_file(self, extension: str) -> Path | None:
        expected = self.download_path(extension)
        if expected.is_file():
            return expected
        candidates = [
            item
            for item in self.workspace.iterdir()
            if item.is_file()
            and item.name.startswith("download.")
            and item.suffix.lower() not in {".part", ".ytdl"}
        ]
        return max(candidates, key=lambda item: item.stat().st_mtime, default=None)

    def commit(self, candidate: Path, destination: Path) -> Path:
        candidate = candidate.resolve()
        candidate.relative_to(self.workspace.resolve())
        if destination.parent.resolve() != self.output_directory:
            raise OSError("Final destination is outside the selected output directory")
        with _COMMIT_LOCK:
            while True:
                final_path = ensure_unique_path(destination)
                try:
                    if os.name == 'nt':
                        # Windows rename refuses an existing target, including a
                        # file created by another process after name selection.
                        candidate.rename(final_path)
                    else:
                        os.link(candidate, final_path)
                        candidate.unlink()
                    return final_path
                except FileExistsError:
                    continue

    def cleanup(self) -> CancellationCleanupReport:
        if not self.workspace.exists() and not self.workspace.is_symlink():
            self._remove_empty_root()
            return CancellationCleanupReport(
                task_id=self.task_id,
                output_directory=str(self.output_directory),
            )
        try:
            resolved_root = self.temporary_root.resolve()
            if resolved_root.parent != self.output_directory:
                raise OSError("Refusing to clean a temporary root outside the output directory")
            if self.workspace.parent != self.temporary_root:
                raise OSError("Refusing to clean an unexpected task workspace")
        except OSError as exc:
            return self._failed_report(exc)

        last_error: OSError | None = None
        delays = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8)
        for delay in delays:
            if delay:
                self.sleeper(delay)
            try:
                if _is_reparse_point(self.workspace):
                    if self.workspace.is_symlink():
                        self.workspace.unlink()
                    else:
                        os.rmdir(self.workspace)
                else:
                    shutil.rmtree(self.workspace)
                self._remove_empty_root()
                return CancellationCleanupReport(
                    task_id=self.task_id,
                    output_directory=str(self.output_directory),
                )
            except FileNotFoundError:
                self._remove_empty_root()
                return CancellationCleanupReport(
                    task_id=self.task_id,
                    output_directory=str(self.output_directory),
                )
            except OSError as exc:
                last_error = exc
        assert last_error is not None
        logger.error("Failed to clean task workspace %s: %s", self.workspace, last_error)
        return self._failed_report(last_error)

    def _remove_empty_root(self) -> None:
        try:
            self.temporary_root.rmdir()
        except (FileNotFoundError, OSError):
            pass

    def _failed_report(self, error: OSError) -> CancellationCleanupReport:
        return CancellationCleanupReport(
            task_id=self.task_id,
            output_directory=str(self.output_directory),
            failed_paths=(str(self.workspace),),
            errors=(str(error),),
        )

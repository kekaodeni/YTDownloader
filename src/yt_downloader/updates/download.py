from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import threading
import uuid
from typing import Callable

from yt_downloader.updates.models import UpdateManifest, VerifiedUpdatePackage


class UpdatePackageDownloader:
    def __init__(self, open_stream: Callable, *, free_space: Callable[[Path], int] | None = None) -> None:
        self.open_stream = open_stream
        self.free_space = free_space or (lambda path: shutil.disk_usage(path).free)
        self._response_lock = threading.Lock()
        self._active_response = None

    def _set_active_response(self, response) -> None:
        with self._response_lock:
            self._active_response = response

    def cancel_current(self) -> None:
        with self._response_lock:
            response = self._active_response
        if response is not None:
            response.close()

    def download(
        self,
        manifest: UpdateManifest,
        staging_root: Path,
        progress: Callable[[tuple[int, int]], None],
        cancel: threading.Event,
        *,
        backup_size: int,
        margin: int,
        verification_callback: Callable[[], None] | None = None,
    ) -> VerifiedUpdatePackage:
        staging_root = staging_root.resolve()
        staging_root.mkdir(parents=True, exist_ok=True)
        required = (
            manifest.package.compressed_size + manifest.package.extracted_size
            + max(0, backup_size) + max(0, margin)
        )
        if self.free_space(staging_root) < required:
            raise OSError('Insufficient disk space for package, candidate, backup, and margin')
        transaction_id = uuid.uuid4().hex
        transaction = staging_root / f'update-{transaction_id}'
        transaction.mkdir()
        partial = transaction / (manifest.package.name + '.part')
        final = transaction / manifest.package.name
        response = None
        try:
            response = self.open_stream(manifest.package.url, (10, 30))
            self._set_active_response(response)
            digest = hashlib.sha256()
            downloaded = 0
            with partial.open('xb') as output:
                for chunk in response.iter_content(1024 * 256):
                    if cancel.is_set():
                        raise InterruptedError('Update download was cancelled')
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > manifest.package.compressed_size:
                        raise ValueError('Download exceeds signed size')
                    output.write(chunk)
                    digest.update(chunk)
                    progress((downloaded, manifest.package.compressed_size))
            if downloaded != manifest.package.compressed_size:
                raise ValueError('Download does not match signed size')
            if verification_callback is not None:
                verification_callback()
            if digest.hexdigest() != manifest.package.sha256:
                raise ValueError('Download SHA256 does not match signed manifest')
            partial.replace(final)
            return VerifiedUpdatePackage(transaction_id, final, manifest)
        except BaseException:
            self._remove_owned(transaction, staging_root)
            raise
        finally:
            with self._response_lock:
                if self._active_response is response:
                    self._active_response = None
            if response is not None:
                response.close()

    @staticmethod
    def _remove_owned(transaction: Path, root: Path) -> None:
        try:
            resolved = transaction.resolve(strict=False)
            if resolved.parent != root:
                raise ValueError('Update transaction escaped staging root')
            if transaction.exists():
                attributes = getattr(transaction.stat(follow_symlinks=False), 'st_file_attributes', 0)
                if transaction.is_symlink() or attributes & 0x400:
                    raise ValueError('Update transaction became a reparse point')
                shutil.rmtree(transaction)
        except FileNotFoundError:
            return

"""Strict extraction and ownership validation for signed update packages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile
import re

from yt_downloader.updates.protocol import HELPER_PATHS, INTERNAL_LAYOUT, LEGACY_LAYOUT


_DEVICE_NAMES = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
_CRITICAL_FILES = {'YTDownloader.exe', 'BUILD-INFO.json', 'SHA256SUMS.json'}


class SafePackageExtractor:
    """Extract an owned onedir package without following archive-controlled paths."""

    def extract(
        self,
        package: Path,
        candidate: Path,
        *,
        signed_extracted_size: int,
        expected_version: str,
        expected_layout: str | None = None,
    ) -> Path:
        package = package.resolve(strict=True)
        candidate = candidate.resolve(strict=False)
        if candidate.exists():
            raise FileExistsError(f'Candidate already exists: {candidate}')
        try:
            with zipfile.ZipFile(package) as archive:
                files = self._validated_members(archive, signed_extracted_size)
                candidate.mkdir(parents=True, exist_ok=False)
                for info, relative in files:
                    target = candidate / Path(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
            self.validate_tree(candidate, expected_version=expected_version, expected_layout=expected_layout)
            return candidate
        except BaseException:
            self._remove_created_candidate(candidate)
            raise

    @staticmethod
    def _validated_members(archive: zipfile.ZipFile, signed_size: int) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
        if signed_size < 0:
            raise ValueError('Invalid signed extracted size')
        result: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        names: set[str] = set()
        total = 0
        for info in archive.infolist():
            raw = info.filename.replace('\\', '/')
            if raw.startswith('/') or '//' in raw or '\x00' in raw:
                raise ValueError(f'Unsafe absolute archive entry: {raw!r}')
            path = PurePosixPath(raw)
            if not path.parts or path.parts[0] != 'YTDownloader':
                raise ValueError('Every package entry must be under YTDownloader/')
            relative = PurePosixPath(*path.parts[1:])
            if not relative.parts:
                continue
            if any(part in {'', '.', '..'} for part in relative.parts):
                raise ValueError(f'Unsafe archive traversal: {raw!r}')
            for part in relative.parts:
                if ':' in part or part.rstrip(' .') != part:
                    raise ValueError(f'Unsafe Windows archive name: {raw!r}')
                if part.split('.', 1)[0].upper() in _DEVICE_NAMES:
                    raise ValueError(f'Reserved Windows device name: {raw!r}')
            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ValueError(f'Archive links are not allowed: {raw!r}')
            if info.is_dir():
                continue
            folded = relative.as_posix().casefold()
            if folded in names:
                raise ValueError(f'Case-insensitive duplicate archive entry: {raw!r}')
            names.add(folded)
            total += info.file_size
            if total > signed_size:
                raise ValueError('Archive extracted size exceeds signed size')
            result.append((info, relative))
        if total != signed_size:
            raise ValueError('Archive extracted size does not match signed size')
        return result

    @classmethod
    def validate_tree(cls, root: Path, *, expected_version: str | None = None, expected_layout: str | None = None) -> None:
        if root.is_symlink() or cls._is_reparse(root):
            raise ValueError('Package root is a link or reparse point')
        root = root.resolve(strict=True)
        for critical in _CRITICAL_FILES:
            if not (root / critical).is_file():
                raise ValueError(f'Package critical file is missing: {critical}')
        build_info = cls._load_json(root / 'BUILD-INFO.json')
        if not isinstance(build_info, dict):
            raise ValueError('Invalid build metadata')
        layout = cls.layout(build_info)
        if expected_layout is not None and layout != expected_layout:
            raise ValueError('Package helper layout does not match signed manifest')
        helper = HELPER_PATHS[layout]
        if not (root / helper).is_file():
            raise ValueError('Package critical helper is missing')
        for other_layout, other_path in HELPER_PATHS.items():
            if other_layout != layout and (root / other_path).exists():
                raise ValueError('Mixed helper layout is not allowed')
        if expected_version is not None and build_info.get('app_version') != expected_version:
            raise ValueError('Package build version does not match the signed manifest')
        entries = cls._load_json(root / 'SHA256SUMS.json')
        if not isinstance(entries, list):
            raise ValueError('Package ownership manifest must be an array')
        owned: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'Path', 'SHA256'}:
                raise ValueError('Invalid package ownership record')
            relative = cls._safe_manifest_path(entry['Path'])
            folded = relative.as_posix().casefold()
            if folded in owned:
                raise ValueError('Duplicate package ownership record')
            sha256 = entry['SHA256']
            if not isinstance(sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', sha256):
                raise ValueError('Invalid package ownership hash')
            owned[folded] = sha256.lower()
        actual: dict[str, Path] = {}
        for path in root.rglob('*'):
            if path.is_symlink() or cls._is_reparse(path):
                raise ValueError('Package tree contains a link or reparse point')
            if path.is_file() and path != root / 'SHA256SUMS.json':
                relative = path.relative_to(root).as_posix()
                actual[relative.casefold()] = path
        if set(actual) != set(owned):
            raise ValueError('Package contains missing or unknown unowned files')
        for key, path in actual.items():
            digest = cls.file_hash(path)
            if digest != owned[key]:
                raise ValueError(f'Package file hash mismatch: {path.relative_to(root)}')

    @staticmethod
    def layout(build_info: dict) -> str:
        layout = build_info.get('helper_layout', LEGACY_LAYOUT)
        if layout not in HELPER_PATHS:
            raise ValueError('Unsupported helper layout')
        if 'helper_layout' in build_info:
            required = [2] if layout == INTERNAL_LAYOUT else [1, 2]
            if (build_info.get('updater_version') != build_info.get('app_version')
                    or build_info.get('supported_update_protocols') != required
                    or build_info.get('updater_protocol') != (2 if layout == INTERNAL_LAYOUT else 1)):
                raise ValueError('Inconsistent helper layout metadata')
        return layout

    @staticmethod
    def file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _load_json(path: Path):
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f'Invalid package metadata: {path.name}') from exc

    @staticmethod
    def _safe_manifest_path(value: object) -> PurePosixPath:
        if not isinstance(value, str) or '\\' in value or value.startswith('/') or ':' in value:
            raise ValueError('Unsafe package ownership path')
        path = PurePosixPath(value)
        if not path.parts or any(part in {'', '.', '..'} for part in path.parts):
            raise ValueError('Unsafe package ownership path')
        return path

    @staticmethod
    def _is_reparse(path: Path) -> bool:
        try:
            return bool(getattr(path.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400)
        except FileNotFoundError:
            return False

    @staticmethod
    def _remove_created_candidate(candidate: Path) -> None:
        if candidate.exists() and not candidate.is_symlink() and not SafePackageExtractor._is_reparse(candidate):
            shutil.rmtree(candidate)

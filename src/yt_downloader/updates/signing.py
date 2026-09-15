"""Release-side Ed25519 manifest signing; never imported by the desktop app."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from semver import Version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def create_signed_release_assets(
    *,
    package: Path,
    private_key_path: Path,
    password: bytes,
    key_id: str,
    trusted_keys: dict[str, bytes],
    repo_root: Path,
    version: str,
    minimum_auto_update_version: str,
    notes_zh_cn: str,
    notes_en: str,
    published_at: str | None = None,
    acceptance_report_path: Path | None = None,
) -> tuple[bytes, bytes]:
    package = package.resolve(strict=True)
    key_path = private_key_path.resolve(strict=True)
    root = repo_root.resolve(strict=True)
    try:
        key_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError('Release private key must be stored outside the repository')
    parsed_version = Version.parse(version)
    Version.parse(minimum_auto_update_version)
    expected_name = f'YTDownloader-{parsed_version}-win64.zip'
    if package.name != expected_name:
        raise ValueError('Release ZIP name does not match the version')
    package_digest = _sha256(package)
    if acceptance_report_path is None:
        raise ValueError('A matching independent startup acceptance report is required')
    try:
        acceptance = json.loads(acceptance_report_path.resolve(strict=True).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Independent startup acceptance report is invalid') from exc
    required_checks = {
        'ownership_manifest', 'independent_self_test', 'metadata_helper',
        'gui_smoke', 'updater_windowed', 'startup_health',
    }
    checks = acceptance.get('checks') if isinstance(acceptance, dict) else None
    if (
        not isinstance(acceptance, dict)
        or not isinstance(checks, dict)
        or acceptance.get('schema_version') != 1
        or acceptance.get('app_version') != str(parsed_version)
        or acceptance.get('validation_only') is not False
        or acceptance.get('package_name') != expected_name
        or acceptance.get('package_sha256') != package_digest
        or set(checks) != required_checks
        or not all(value is True for value in checks.values())
    ):
        raise ValueError('Independent startup acceptance report does not match this formal package')
    with zipfile.ZipFile(package) as archive:
        try:
            build_info = json.loads(archive.read('YTDownloader/BUILD-INFO.json').decode('utf-8-sig'))
        except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('Release ZIP has no valid BUILD-INFO.json') from exc
        if build_info.get('app_version') != str(parsed_version) or build_info.get('validation_only') is not False:
            raise ValueError('Release ZIP is not a formal build for this version')
        extracted_size = sum(info.file_size for info in archive.infolist() if not info.is_dir())
    if key_id not in trusted_keys:
        raise ValueError('Signing key_id is not trusted by this application version')
    try:
        loaded = serialization.load_pem_private_key(key_path.read_bytes(), password=password)
    except TypeError as exc:
        raise ValueError('Release private key must be encrypted PKCS8') from exc
    except ValueError as exc:
        raise ValueError('Unable to decrypt the release private key') from exc
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError('Release private key must be Ed25519')
    public = loaded.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if public != trusted_keys[key_id]:
        raise ValueError('Signing key does not match the embedded trusted public key')
    published = published_at or datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    base = f'https://github.com/kekaodeni/YTDownloader/releases/download/v{parsed_version}/'
    release_url = f'https://github.com/kekaodeni/YTDownloader/releases/tag/v{parsed_version}'
    payload = {
        'schema_version': 1,
        'app_id': 'YTDownloader', 'channel': 'stable', 'platform': 'windows', 'architecture': 'x64',
        'version': str(parsed_version), 'published_at': published,
        'minimum_auto_update_version': minimum_auto_update_version,
        'updater_protocol': 1, 'key_id': key_id,
        'notes': {'zh-CN': notes_zh_cn, 'en': notes_en},
        'release_url': release_url,
        'package': {
            'name': expected_name, 'url': base + expected_name,
            'compressed_size': package.stat().st_size, 'extracted_size': extracted_size,
            'sha256': package_digest,
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    detached = base64.b64encode(loaded.sign(raw))
    _atomic_write(package.parent / 'update-manifest.json', raw)
    _atomic_write(package.parent / 'update-manifest.sig', detached)
    return raw, detached


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

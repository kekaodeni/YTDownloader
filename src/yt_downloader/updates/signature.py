from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime
from collections.abc import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from semver import Version

from yt_downloader.updates.models import UpdateManifest, UpdatePackage, UpdateRelease


_TOP_FIELDS = {
    'schema_version', 'app_id', 'channel', 'platform', 'architecture', 'version',
    'published_at', 'minimum_auto_update_version', 'updater_protocol', 'key_id',
    'notes', 'release_url', 'package',
}
_PACKAGE_FIELDS = {'name', 'url', 'compressed_size', 'extracted_size', 'sha256'}
_NOTES_FIELDS = {'zh-CN', 'en'}


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _exact_fields(value: Mapping, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f'{label} fields are missing or unknown')


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label} must be non-empty text')
    return value


def _positive_int(value, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f'{label} must be a positive integer')
    return value


class TrustedKeyring:
    """Immutable trust roots compiled into a particular application version."""

    def __init__(self, keys: Mapping[str, bytes]) -> None:
        self._keys = {str(key): Ed25519PublicKey.from_public_bytes(bytes(value)) for key, value in keys.items()}

    def verify(self, raw_manifest: bytes, detached_signature: bytes, release: UpdateRelease) -> UpdateManifest:
        try:
            payload = json.loads(raw_manifest.decode('utf-8'), object_pairs_hook=_strict_object)
        except UnicodeDecodeError as exc:
            raise ValueError('Manifest must be UTF-8') from exc
        if not isinstance(payload, Mapping):
            raise ValueError('Manifest must be an object')
        _exact_fields(payload, _TOP_FIELDS, 'Manifest')
        if type(payload['schema_version']) is not int or payload['schema_version'] != 1:
            raise ValueError('Manifest schema is unsupported')
        if (payload['app_id'], payload['channel'], payload['platform'], payload['architecture']) != (
            'YTDownloader', 'stable', 'windows', 'x64'
        ):
            raise ValueError('Manifest identity or platform does not match this application')
        key_id = _text(payload['key_id'], 'key_id')
        public_key = self._keys.get(key_id)
        if public_key is None:
            raise ValueError('Manifest key_id is not trusted by this application version')
        try:
            signature = base64.b64decode(detached_signature, validate=True)
            public_key.verify(signature, raw_manifest)
        except (InvalidSignature, ValueError, binascii.Error) as exc:
            raise ValueError('Manifest signature is invalid') from exc
        version = Version.parse(_text(payload['version'], 'version'))
        if version != release.version or release.tag != f'v{version}':
            raise ValueError('Release tag and manifest version do not match')
        release_url = _text(payload['release_url'], 'release_url')
        if release_url != release.release_url:
            raise ValueError('Release URL and manifest version do not match')
        notes = payload['notes']
        package = payload['package']
        if not isinstance(notes, Mapping) or not isinstance(package, Mapping):
            raise ValueError('Manifest notes and package must be objects')
        _exact_fields(notes, _NOTES_FIELDS, 'Notes')
        _exact_fields(package, _PACKAGE_FIELDS, 'Package')
        name = _text(package['name'], 'package name')
        expected_name = f'YTDownloader-{version}-win64.zip'
        prefix = f'https://github.com/kekaodeni/YTDownloader-releases/releases/download/v{version}/'
        url = _text(package['url'], 'package URL')
        if name != expected_name or url != prefix + expected_name:
            raise ValueError('Package name, URL, and manifest version do not match')
        digest = _text(package['sha256'], 'SHA256').lower()
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('SHA256 is malformed')
        published_at = _text(payload['published_at'], 'published_at')
        try:
            published = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('published_at must be an ISO-8601 timestamp') from exc
        if published.tzinfo is None:
            raise ValueError('published_at must include a timezone')
        return UpdateManifest(
            version=version,
            published_at=published_at,
            minimum_auto_update_version=Version.parse(_text(payload['minimum_auto_update_version'], 'minimum version')),
            updater_protocol=_positive_int(payload['updater_protocol'], 'updater protocol'),
            key_id=key_id,
            notes_zh_cn=_text(notes['zh-CN'], 'Chinese notes'),
            notes_en=_text(notes['en'], 'English notes'),
            release_url=release_url,
            package=UpdatePackage(
                name=name, url=url,
                compressed_size=_positive_int(package['compressed_size'], 'compressed size'),
                extracted_size=_positive_int(package['extracted_size'], 'extracted size'),
                sha256=digest,
            ),
        )

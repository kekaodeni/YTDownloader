import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from yt_downloader.updates.models import UpdateRelease
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS
from semver import Version


def manifest(key_id='current-key'):
    version = '0.4.1'
    return {
        'schema_version': 1, 'app_id': 'YTDownloader', 'channel': 'stable',
        'platform': 'windows', 'architecture': 'x64', 'version': version,
        'published_at': '2026-09-04T12:00:00Z', 'minimum_auto_update_version': '0.4.0',
        'updater_protocol': 1, 'key_id': key_id,
        'notes': {'zh-CN': '安全更新', 'en': 'Security update'},
        'release_url': f'https://github.com/kekaodeni/YTDownloader-releases/releases/tag/v{version}',
        'package': {
            'name': f'YTDownloader-{version}-win64.zip',
            'url': f'https://github.com/kekaodeni/YTDownloader-releases/releases/download/v{version}/YTDownloader-{version}-win64.zip',
            'compressed_size': 100, 'extracted_size': 300, 'sha256': 'a' * 64,
        },
    }


def signed(payload, private):
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    return raw, base64.b64encode(private.sign(raw))


def release():
    return UpdateRelease(Version.parse('0.4.1'), 'v0.4.1', 'manifest', 'signature', manifest()['release_url'])


def key_bytes(private):
    return private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def test_production_trusted_key_is_the_approved_ed25519_public_key():
    assert set(PRODUCTION_TRUSTED_KEYS) == {'yt-downloader-prod-2026'}
    public = PRODUCTION_TRUSTED_KEYS['yt-downloader-prod-2026']
    assert len(public) == 32
    Ed25519PublicKey.from_public_bytes(public)
    assert hashlib.sha256(public).hexdigest() == (
        'd7ed7bd453f35861dee0453d9f805e595e9797cbc1626a8bb59b7488fa037152'
    )


def test_verifies_raw_manifest_and_supports_preloaded_rotation_key():
    old = Ed25519PrivateKey.generate(); future = Ed25519PrivateKey.generate()
    ring = TrustedKeyring({'old-key': key_bytes(old), 'future-key': key_bytes(future)})
    raw, signature = signed(manifest('future-key'), future)
    verified = ring.verify(raw, signature, release())
    assert str(verified.version) == '0.4.1'
    assert verified.package.compressed_size == 100
    assert verified.key_id == 'future-key'


@pytest.mark.parametrize('mutation', ['manifest', 'signature'])
def test_rejects_tampered_manifest_or_signature(mutation):
    private = Ed25519PrivateKey.generate(); ring = TrustedKeyring({'current-key': key_bytes(private)})
    raw, signature = signed(manifest(), private)
    if mutation == 'manifest': raw += b' '
    else: signature = base64.b64encode(b'0' * 64)
    with pytest.raises(ValueError, match='signature'):
        ring.verify(raw, signature, release())


def test_rejects_duplicate_json_keys_and_unknown_remote_key():
    private = Ed25519PrivateKey.generate()
    duplicate = b'{"schema_version":1,"schema_version":1}'
    with pytest.raises(ValueError, match='Duplicate'):
        TrustedKeyring({'current-key': key_bytes(private)}).verify(duplicate, b'', release())
    raw, signature = signed(manifest('remote-key'), private)
    with pytest.raises(ValueError, match='not trusted'):
        TrustedKeyring({'current-key': key_bytes(private)}).verify(raw, signature, release())


def test_rejects_unknown_fields_and_release_version_mismatch():
    private = Ed25519PrivateKey.generate(); ring = TrustedKeyring({'current-key': key_bytes(private)})
    payload = manifest(); payload['remote_trust_root'] = 'never'
    raw, signature = signed(payload, private)
    with pytest.raises(ValueError, match='fields'):
        ring.verify(raw, signature, release())
    payload = manifest(); payload['version'] = '0.4.2'
    raw, signature = signed(payload, private)
    with pytest.raises(ValueError, match='version'):
        ring.verify(raw, signature, release())

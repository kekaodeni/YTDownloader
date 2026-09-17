import base64
import hashlib
import json
from pathlib import Path
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from semver import Version

from yt_downloader.updates.models import UpdateRelease
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.signing import create_signed_release_assets


def _formal_zip(path: Path, version='0.4.0'):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('YTDownloader/BUILD-INFO.json', json.dumps({'app_version':version,'validation_only':False}))
        archive.writestr('YTDownloader/YTDownloader.exe', b'app')
        archive.writestr('YTDownloader/YTDownloaderUpdater.exe', b'updater')


def _acceptance(path: Path, package: Path, *, validation_only=False):
    path.write_text(json.dumps({
        'schema_version': 1, 'app_version': '0.4.0',
        'validation_only': validation_only, 'package_name': package.name,
        'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
        'checks': {
            'ownership_manifest': True, 'independent_self_test': True,
            'metadata_helper': True, 'gui_smoke': True,
            'updater_windowed': True, 'startup_health': True,
        },
    }), encoding='utf-8')
    return path


def test_signing_uses_encrypted_external_ed25519_key_and_creates_verifiable_assets(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir(); package=repo/'YTDownloader-0.4.0-win64.zip'; _formal_zip(package)
    key=Ed25519PrivateKey.generate(); public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    key_path=tmp_path/'release-key.pem'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(b'secret')))
    acceptance=_acceptance(tmp_path/'acceptance.json',package)
    raw, detached=create_signed_release_assets(
        package=package, private_key_path=key_path, password=b'secret', key_id='prod-2026',
        trusted_keys={'prod-2026':public}, repo_root=repo, version='0.4.0',
        minimum_auto_update_version='0.4.0', notes_zh_cn='安全更新', notes_en='Secure update',
        published_at='2026-09-04T10:00:00Z',
        acceptance_report_path=acceptance,
    )
    release=UpdateRelease(
        Version.parse('0.4.0'),'v0.4.0',
        'https://github.com/kekaodeni/YTDownloader/releases/download/v0.4.0/update-manifest.json',
        'https://github.com/kekaodeni/YTDownloader/releases/download/v0.4.0/update-manifest.sig',
        'https://github.com/kekaodeni/YTDownloader/releases/tag/v0.4.0',
    )
    manifest=TrustedKeyring({'prod-2026':public}).verify(raw,detached,release)
    assert manifest.package.name==package.name
    assert (repo/'update-manifest.json').read_bytes()==raw
    assert base64.b64decode((repo/'update-manifest.sig').read_bytes(),validate=True)


def test_signing_refuses_unencrypted_or_untrusted_keys(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();package=repo/'YTDownloader-0.4.0-win64.zip';_formal_zip(package)
    key=Ed25519PrivateKey.generate();key_path=tmp_path/'key.pem'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    acceptance=_acceptance(tmp_path/'acceptance.json',package)
    with pytest.raises(ValueError,match='encrypted'):
        create_signed_release_assets(
            package=package,private_key_path=key_path,password=b'secret',key_id='prod-2026',trusted_keys={'prod-2026':public},
            repo_root=repo,version='0.4.0',minimum_auto_update_version='0.4.0',notes_zh_cn='zh',notes_en='en',
            published_at='2026-09-04T10:00:00Z',
            acceptance_report_path=acceptance,
        )
    with pytest.raises(ValueError,match='not trusted'):
        create_signed_release_assets(
            package=package,private_key_path=key_path,password=b'secret',key_id='unknown',trusted_keys={},
            repo_root=repo,version='0.4.0',minimum_auto_update_version='0.4.0',notes_zh_cn='zh',notes_en='en',
            published_at='2026-09-04T10:00:00Z',
            acceptance_report_path=acceptance,
        )


def test_signing_refuses_missing_or_mismatched_acceptance_report(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();package=repo/'YTDownloader-0.4.0-win64.zip';_formal_zip(package)
    key=Ed25519PrivateKey.generate();key_path=tmp_path/'key.pem'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(b'secret')))
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    arguments=dict(
        package=package,private_key_path=key_path,password=b'secret',key_id='prod',trusted_keys={'prod':public},
        repo_root=repo,version='0.4.0',minimum_auto_update_version='0.4.0',notes_zh_cn='zh',notes_en='en',
        published_at='2026-09-04T10:00:00Z',
    )
    with pytest.raises(ValueError,match='acceptance report is required'):
        create_signed_release_assets(**arguments)
    report=_acceptance(tmp_path/'acceptance.json',package,validation_only=True)
    with pytest.raises(ValueError,match='does not match'):
        create_signed_release_assets(**arguments,acceptance_report_path=report)


def test_signing_schema_two_requires_internal_layout_and_emits_contract(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();package=repo/'YTDownloader-0.5.0-win64.zip'
    with zipfile.ZipFile(package,'w') as archive:
        archive.writestr('YTDownloader/BUILD-INFO.json', json.dumps({'app_version':'0.5.0','validation_only':False,'helper_layout':'internal-v1'}))
        archive.writestr('YTDownloader/YTDownloader.exe', b'app')
        archive.writestr('YTDownloader/_internal/updater/YTDownloaderUpdater.exe', b'updater')
    key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    key_path=tmp_path/'key.pem'; key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(b'secret')))
    acceptance=_acceptance(tmp_path/'acceptance.json',package); acceptance_data=json.loads(acceptance.read_text()); acceptance_data['app_version']='0.5.0'; acceptance_data['package_name']=package.name; acceptance_data['package_sha256']=hashlib.sha256(package.read_bytes()).hexdigest(); acceptance.write_text(json.dumps(acceptance_data))
    raw,_=create_signed_release_assets(package=package,private_key_path=key_path,password=b'secret',key_id='prod',trusted_keys={'prod':public},repo_root=repo,version='0.5.0',minimum_auto_update_version='0.4.2',minimum_updater_version='0.4.2',notes_zh_cn='zh',notes_en='en',published_at='2026-09-17T00:00:00Z',acceptance_report_path=acceptance,schema_version=2)
    data=json.loads(raw); assert data['schema_version']==2 and data['helper_layout']=='internal-v1' and data['package']['kind']=='standard'

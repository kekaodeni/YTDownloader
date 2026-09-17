from datetime import datetime, timezone
import hashlib
import json
import threading

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from semver import Version

from yt_downloader.updates.models import UpdateCapability, UpdateRelease, UpdateState
from yt_downloader.updates.service import UpdateService
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.state import UpdatePersistentState, UpdateStateStore


class ImmediateRunner:
    def start(self, worker):
        worker.run()


def _signed_release(data=b'package'):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    version = Version.parse('0.4.1')
    release_url = 'https://github.com/kekaodeni/YTDownloader/releases/tag/v0.4.1'
    package_url = 'https://github.com/kekaodeni/YTDownloader/releases/download/v0.4.1/YTDownloader-0.4.1-win64.zip'
    payload = {
        'schema_version': 1, 'app_id': 'YTDownloader', 'channel': 'stable',
        'platform': 'windows', 'architecture': 'x64', 'version': '0.4.1',
        'published_at': '2026-09-04T10:00:00Z', 'minimum_auto_update_version': '0.4.0',
        'updater_protocol': 1, 'key_id': 'test',
        'notes': {'zh-CN': '修复与改进', 'en': 'Fixes and improvements'},
        'release_url': release_url,
        'package': {'name': 'YTDownloader-0.4.1-win64.zip', 'url': package_url,
                    'compressed_size': len(data), 'extracted_size': 100,
                    'sha256': hashlib.sha256(data).hexdigest()},
    }
    raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()
    import base64
    signature = base64.b64encode(key.sign(raw))
    release = UpdateRelease(
        version, 'v0.4.1',
        package_url.rsplit('/', 1)[0] + '/update-manifest.json',
        package_url.rsplit('/', 1)[0] + '/update-manifest.sig', release_url,
    )
    return release, raw, signature, public


def test_check_verifies_manifest_and_persists_last_check(qtbot, tmp_path):
    release, raw, signature, public = _signed_release()
    class Discovery:
        def check(self, current): assert current == '0.4.0'; return (release,)
    fetched = {release.manifest_url: raw, release.signature_url: signature}
    service = UpdateService(
        current_version='0.4.0', discovery=Discovery(), fetch_bytes=fetched.__getitem__,
        keyring=TrustedKeyring({'test': public}), state_store=UpdateStateStore(tmp_path/'state.json'),
        downloader=None, staging_root=tmp_path/'staging', capability=UpdateCapability.CHECK_ONLY,
        runner=ImmediateRunner(), now=lambda: datetime(2026, 9, 4, 10, tzinfo=timezone.utc),
    )
    available = []
    service.update_available.connect(available.append)
    assert service.check(manual=True)
    assert service.state is UpdateState.AVAILABLE
    assert available[0].version == Version.parse('0.4.1')
    assert UpdateStateStore(tmp_path/'state.json').load().last_checked_at


def test_automatic_check_is_throttled_but_manual_check_is_not(tmp_path):
    store = UpdateStateStore(tmp_path/'state.json')
    store.save(UpdatePersistentState(last_checked_at='2026-09-04T09:00:00+00:00'))
    calls = []
    class Discovery:
        def check(self, _current): calls.append(1); return None
    service = UpdateService(
        current_version='0.4.0', discovery=Discovery(), fetch_bytes=lambda _url: b'',
        keyring=TrustedKeyring({}), state_store=store, downloader=None,
        staging_root=tmp_path/'staging', capability=UpdateCapability.CHECK_ONLY,
        runner=ImmediateRunner(), now=lambda: datetime(2026, 9, 4, 10, tzinfo=timezone.utc),
    )
    assert not service.check(manual=False)
    assert service.check(manual=True)
    assert calls == [1]


def test_manual_failures_are_identified_for_visible_error_ui(tmp_path):
    class Discovery:
        def check(self, _current): raise TimeoutError('network timeout')
    service = UpdateService(
        current_version='0.4.0', discovery=Discovery(), fetch_bytes=lambda _url: b'',
        keyring=TrustedKeyring({}), state_store=UpdateStateStore(tmp_path/'state.json'),
        downloader=None, staging_root=tmp_path/'staging', capability=UpdateCapability.CHECK_ONLY,
        runner=ImmediateRunner(), now=lambda: datetime.now(timezone.utc),
    )
    failures = []
    service.failed.connect(lambda error, manual: failures.append((error, manual)))
    service.check(manual=True)
    assert service.state is UpdateState.FAILED
    assert failures[0][1] is True
    assert 'network timeout' in failures[0][0].technical_message


def test_cancel_moves_to_cancelling_and_closes_downloader(tmp_path):
    class CapturingRunner:
        def start(self, worker): self.worker = worker
    class Downloader:
        cancelled = False
        def cancel_current(self): self.cancelled = True
    runner = CapturingRunner(); downloader = Downloader()
    service = UpdateService(
        current_version='0.4.0', discovery=None, fetch_bytes=lambda _url: b'',
        keyring=TrustedKeyring({}), state_store=UpdateStateStore(tmp_path/'state.json'),
        downloader=downloader, staging_root=tmp_path/'staging',
        capability=UpdateCapability.DOWNLOAD_AND_VERIFY, runner=runner,
    )
    service.manifest = _signed_release()[0]  # non-null marker; worker is deliberately not run
    service.state = UpdateState.AVAILABLE
    assert service.download()
    assert service.cancel()
    assert service.state is UpdateState.CANCELLING
    assert downloader.cancelled


def test_verified_package_can_be_restored_across_restart_only_after_reverification(tmp_path):
    data = b'package'
    release, raw, signature, public = _signed_release(data)
    transaction = tmp_path / 'staging' / 'update-abc'; transaction.mkdir(parents=True)
    (transaction / 'update-manifest.json').write_bytes(raw)
    (transaction / 'update-manifest.sig').write_bytes(signature)
    (transaction / 'YTDownloader-0.4.1-win64.zip').write_bytes(data)
    store = UpdateStateStore(tmp_path / 'state.json')
    store.save(UpdatePersistentState(transaction_id='abc', pending_version='0.4.1'))
    service = UpdateService(
        current_version='0.4.0', discovery=None, fetch_bytes=lambda _url: b'',
        keyring=TrustedKeyring({'test': public}), state_store=store, downloader=None,
        staging_root=tmp_path/'staging', capability=UpdateCapability.DOWNLOAD_AND_VERIFY,
        runner=ImmediateRunner(),
    )
    assert service.restore_verified_package()
    assert service.state is UpdateState.READY_TO_INSTALL
    (transaction / 'YTDownloader-0.4.1-win64.zip').write_bytes(b'tampered')
    service2 = UpdateService(
        current_version='0.4.0', discovery=None, fetch_bytes=lambda _url: b'',
        keyring=TrustedKeyring({'test': public}), state_store=store, downloader=None,
        staging_root=tmp_path/'staging', capability=UpdateCapability.DOWNLOAD_AND_VERIFY,
        runner=ImmediateRunner(),
    )
    assert not service2.restore_verified_package()
    assert service2.verified_package is None

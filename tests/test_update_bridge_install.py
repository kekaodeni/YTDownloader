import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from yt_downloader.updates.archive import SafePackageExtractor


def write_tree(root, version='0.5.0', layout='internal-v1'):
    root.mkdir(parents=True, exist_ok=True)
    helper = '_internal/updater/YTDownloaderUpdater.exe' if layout == 'internal-v1' else 'YTDownloaderUpdater.exe'
    info = {'app_version': version, 'validation_only': False, 'helper_layout': layout,
            'updater_version': version, 'updater_protocol': 2 if layout == 'internal-v1' else 1,
            'supported_update_protocols': [2] if layout == 'internal-v1' else [1, 2]}
    for name, value in {'YTDownloader.exe': version.encode(), helper: b'controlled-helper',
                        'BUILD-INFO.json': json.dumps(info).encode()}.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
    write_sums(root)
    return root


def write_sums(root):
    (root/'SHA256SUMS.json').write_text(json.dumps([
        {'Path': path.relative_to(root).as_posix(), 'SHA256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(root.rglob('*')) if path.is_file() and path.name != 'SHA256SUMS.json'
    ]), encoding='utf-8')


def test_internal_bundle_validates_without_root_helper(tmp_path):
    root = write_tree(tmp_path/'app')
    SafePackageExtractor.validate_tree(root, expected_version='0.5.0')
    assert not (root/'YTDownloaderUpdater.exe').exists()
    (root/'YTDownloaderUpdater.exe').write_bytes(b'extra')
    write_sums(root)
    with pytest.raises(ValueError, match='layout'):
        SafePackageExtractor.validate_tree(root)


def staged_service(tmp_path, current='0.4.2', target='0.5.0'):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from test_update_bridge_protocol import payload, release_for
    from test_update_signature import signed, key_bytes
    from yt_downloader.updates.models import UpdateCapability, VerifiedUpdatePackage
    from yt_downloader.updates.service import UpdateService
    from yt_downloader.updates.state import UpdateStateStore
    from yt_downloader.updates.signature import TrustedKeyring
    install = write_tree(tmp_path/'installed', current, 'legacy-root' if current == '0.4.2' else 'internal-v1')
    data = tmp_path/'data'; transaction = data/'update-staging/update-test'; transaction.mkdir(parents=True)
    candidate = write_tree(tmp_path/'source', target)
    info = payload(target)
    package = transaction/info['package']['name']
    with zipfile.ZipFile(package, 'w') as archive:
        for path in candidate.rglob('*'):
            if path.is_file(): archive.write(path, 'YTDownloader/'+path.relative_to(candidate).as_posix())
    info['package'].update(compressed_size=package.stat().st_size,
        extracted_size=sum(p.stat().st_size for p in candidate.rglob('*') if p.is_file()),
        sha256=SafePackageExtractor.file_hash(package))
    key=Ed25519PrivateKey.generate(); ring=TrustedKeyring({'test':key_bytes(key)})
    raw,sig=signed(info,key)
    (transaction/'update-manifest.json').write_bytes(raw); (transaction/'update-manifest.sig').write_bytes(sig)
    manifest=ring.verify(raw,sig,release_for(info))
    service=UpdateService(current_version=current,discovery=None,fetch_bytes=lambda _: b'',keyring=ring,
        state_store=UpdateStateStore(data/'update-state.json'),downloader=None,staging_root=transaction.parent,
        capability=UpdateCapability.AUTO_INSTALL)
    service.verified_package=VerifiedUpdatePackage('test',package,manifest)
    return service,install,data,transaction


@pytest.mark.parametrize('current,target', [('0.4.2','0.5.0'),('0.5.0','0.5.1')])
def test_preparation_stages_only_verified_installed_helper(tmp_path,current,target):
    service,install,data,transaction=staged_service(tmp_path,current,target)
    command=service.prepare_install_command(install,data,42)
    assert Path(command[0]) == transaction/'updater/YTDownloaderUpdater.exe'
    assert Path(command[0]).read_bytes() == b'controlled-helper'
    assert (transaction/'install-request.json').is_file()
    service.verified_package.path.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='size|hash'):
        service.prepare_install_command(install,data,42)


def test_helper_independently_rejects_changed_transaction_identity(tmp_path):
    from yt_downloader.updates.installation import InstallRequest, validate_request
    service,install,data,transaction=staged_service(tmp_path)
    command=service.prepare_install_command(install,data,42)
    request=InstallRequest(transaction,install,data,'0.4.2','0.5.0',42)
    assert str(validate_request(request,service.keyring,executing_helper=Path(command[0])).version) == '0.5.0'
    binding=json.loads((transaction/'install-request.json').read_text())
    binding['original_pid']=43
    (transaction/'install-request.json').write_text(json.dumps(binding))
    with pytest.raises(ValueError,match='identity'):
        validate_request(request,service.keyring,executing_helper=Path(command[0]))


def test_install_preparation_runs_as_worker_before_exit_signal(tmp_path):
    from yt_downloader.updates.models import UpdateState
    service,install,data,transaction=staged_service(tmp_path)
    class Runner:
        def start(self,worker): self.worker=worker
    service.runner=Runner(); service.state=UpdateState.READY_TO_INSTALL
    ready=[]; service.install_prepared.connect(ready.append)
    assert service.prepare_install(install,data,42)
    assert service.state == UpdateState.PREPARING_INSTALL
    assert not ready and not (transaction/'updater').exists()
    service.runner.worker.run()
    assert service.state == UpdateState.PREPARING_EXIT
    assert Path(ready[0][0]).is_file()


def test_bridge_helper_installs_signed_internal_candidate(tmp_path,monkeypatch):
    from yt_downloader_updater import __main__ as entry
    service,install,data,transaction=staged_service(tmp_path)
    command=service.prepare_install_command(install,data,42)
    monkeypatch.setattr(entry,'PRODUCTION_TRUSTED_KEYS',{'test':b'x'*32})
    monkeypatch.setattr(entry,'TrustedKeyring',lambda _:service.keyring)
    monkeypatch.setattr(entry,'UPDATER_VERSION','0.4.2',raising=False)
    monkeypatch.setattr(entry.sys,'executable',command[0])
    installed=[]
    class Installer:
        def install(self,**kwargs):
            SafePackageExtractor.validate_tree(kwargs['candidate_dir'],expected_version='0.5.0')
            assert not (kwargs['candidate_dir']/'YTDownloaderUpdater.exe').exists()
            installed.append(kwargs)
    monkeypatch.setattr(entry,'TransactionalInstaller',Installer)
    assert entry.run(list(command[1:])) == 0
    assert len(installed) == 1


def test_recovery_handles_original_rename_before_journal_write(tmp_path):
    from yt_downloader.updates.transaction import TransactionalInstaller, UpdateTransactionStage
    install=tmp_path/'app'; backup=tmp_path/'.app.backup-update-test'; candidate=tmp_path/'.app.candidate-update-test'
    write_tree(backup,'0.4.2','legacy-root'); write_tree(candidate)
    staging=tmp_path/'update-test'; staging.mkdir()
    (staging/'update-transaction.json').write_text(json.dumps(dict(
        transaction_id='update-test',stage='WAITING_FOR_EXIT',install_dir=str(install),
        candidate_dir=str(candidate),backup_dir=str(backup),health_marker=str(staging/'startup-health.json'),error='')))
    result=TransactionalInstaller().recover(staging)
    assert result.stage == UpdateTransactionStage.ROLLED_BACK
    SafePackageExtractor.validate_tree(install,expected_version='0.4.2')
    assert TransactionalInstaller().recover(staging).stage == UpdateTransactionStage.ROLLED_BACK

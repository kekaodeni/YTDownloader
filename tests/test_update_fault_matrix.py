import hashlib
import json
from pathlib import Path

import pytest

from yt_downloader.updates.archive import SafePackageExtractor
from yt_downloader.updates.http import SecureUpdateHttpClient
from yt_downloader.updates.transaction import TransactionalInstaller


def _tree(root: Path, payload: bytes) -> None:
    root.mkdir()
    files = {
        'YTDownloader.exe': payload,
        'YTDownloaderUpdater.exe': b'updater',
        'BUILD-INFO.json': json.dumps({'app_version': payload.decode()}).encode(),
    }
    for name, value in files.items(): (root / name).write_bytes(value)
    (root / 'SHA256SUMS.json').write_text(json.dumps([
        {'Path': name, 'SHA256': hashlib.sha256(value).hexdigest()}
        for name, value in files.items()
    ]), encoding='utf-8')


def test_candidate_switch_failure_restores_old_version_and_preserves_user_data(tmp_path):
    install=tmp_path/'app'; candidate=tmp_path/'candidate'; staging=tmp_path/'update-tx'; data=tmp_path/'用户数据'
    _tree(install,b'old'); _tree(candidate,b'new'); staging.mkdir(); data.mkdir(); (data/'history.db').write_bytes(b'history')
    calls=[]
    def replace(source, target):
        calls.append((Path(source).name, Path(target).name))
        if Path(source) == candidate:
            raise PermissionError('candidate locked')
        Path(source).replace(target)
    installer=TransactionalInstaller(wait_for_exit=lambda *_:True, replace_path=replace)
    with pytest.raises(PermissionError, match='locked'):
        installer.install(transaction_id='tx', install_dir=install, candidate_dir=candidate,
                          staging_dir=staging, data_dir=data, original_pid=1)
    assert (install/'YTDownloader.exe').read_bytes()==b'old'
    assert (data/'history.db').read_bytes()==b'history'
    assert json.loads((staging/'update-transaction.json').read_text())['stage']=='ROLLED_BACK'


def test_rollback_failure_preserves_backup_and_candidate_with_recovery_journal(tmp_path):
    install=tmp_path/'app'; candidate=tmp_path/'candidate'; staging=tmp_path/'update-tx'; data=tmp_path/'data'
    _tree(install,b'old'); _tree(candidate,b'new'); staging.mkdir(); data.mkdir()
    def replace(source, target):
        source, target = Path(source), Path(target)
        if source.name.startswith('.app.backup-') and target == install:
            raise PermissionError('restore locked')
        source.replace(target)
    installer=TransactionalInstaller(
        wait_for_exit=lambda *_:True,
        launch_health_check=lambda *_:object(), wait_for_health=lambda *_:False,
        terminate_launched=lambda *_:None, replace_path=replace,
    )
    with pytest.raises(RuntimeError, match='rollback'):
        installer.install(transaction_id='tx', install_dir=install, candidate_dir=candidate,
                          staging_dir=staging, data_dir=data, original_pid=1)
    journal=json.loads((staging/'update-transaction.json').read_text())
    assert journal['stage']=='ROLLBACK_FAILED'
    assert Path(journal['backup_dir']).is_dir()
    assert candidate.is_dir()
    assert not install.exists()


def test_existing_transaction_lock_prevents_any_directory_switch(tmp_path):
    install=tmp_path/'app'; candidate=tmp_path/'candidate'; staging=tmp_path/'update-tx'; data=tmp_path/'data'
    _tree(install,b'old'); _tree(candidate,b'new'); staging.mkdir(); data.mkdir()
    (staging/'update-transaction.lock').write_text('owned')
    with pytest.raises(RuntimeError, match='Another update'):
        TransactionalInstaller(wait_for_exit=lambda *_:True).install(
            transaction_id='tx', install_dir=install, candidate_dir=candidate,
            staging_dir=staging, data_dir=data, original_pid=1)
    assert (install/'YTDownloader.exe').read_bytes()==b'old'
    assert (candidate/'YTDownloader.exe').read_bytes()==b'new'


def test_recovery_rejects_tampered_journal_paths(tmp_path):
    staging=tmp_path/'update-tx'; staging.mkdir()
    (staging/'update-transaction.json').write_text(json.dumps({
        'transaction_id':'tx','stage':'WAITING_FOR_HEALTH','install_dir':str(tmp_path/'app'),
        'candidate_dir':str(tmp_path/'candidate'),'backup_dir':str(tmp_path/'elsewhere'),
        'health_marker':str(staging/'startup-health.json'),'error':'',
    }))
    with pytest.raises(ValueError, match='ownership'):
        TransactionalInstaller().recover(staging)


def test_safe_package_supports_unicode_paths_without_weakening_ownership(tmp_path):
    import zipfile
    package=tmp_path/'更新.zip'; candidate=tmp_path/'候选目录'
    files={
        'YTDownloader.exe':b'app','YTDownloaderUpdater.exe':b'updater',
        'BUILD-INFO.json':json.dumps({'app_version':'0.4.1'}).encode(),
        '_internal/中文😀.txt':'内容'.encode(),
    }
    sums=[{'Path':name,'SHA256':hashlib.sha256(value).hexdigest()} for name,value in files.items()]
    files['SHA256SUMS.json']=json.dumps(sums,ensure_ascii=False).encode()
    with zipfile.ZipFile(package,'w') as archive:
        for name,value in files.items(): archive.writestr('YTDownloader/'+name,value)
    SafePackageExtractor().extract(package,candidate,signed_extracted_size=sum(map(len,files.values())),expected_version='0.4.1')
    assert (candidate/'_internal'/'中文😀.txt').read_text(encoding='utf-8')=='内容'


def test_update_redirect_rejects_nonstandard_https_port_and_closes_resources():
    class Response:
        status_code=302; headers={'Location':'https://release-assets.githubusercontent.com:444/asset'}
        closed=False
        def close(self): self.closed=True
    response=Response()
    class Session:
        def __init__(self): self.headers={};self.proxies={};self.cookies=type('C',(),{'clear':lambda self:None})();self.auth=None;self.closed=False
        def get(self,*_args,**_kwargs): return response
        def close(self): self.closed=True
    session=Session(); snapshot=type('S',(),{'mode':'direct','detected_proxies':{},'custom_proxy_url':''})()
    policy=type('P',(),{'snapshot':lambda self:snapshot})()
    client=SecureUpdateHttpClient(policy,session_factory=lambda:session)
    url='https://github.com/kekaodeni/YTDownloader/releases/download/v0.4.1/x.zip'
    with pytest.raises(ValueError,match='443'):
        client.open_stream(url,(10,30))
    assert response.closed and session.closed

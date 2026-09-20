"""Real tag/source frozen bridge matrix with isolated test trust and local transport.

Never publishes, signs production assets, or changes checked-out version files.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from yt_downloader.updates.archive import SafePackageExtractor as Archive

APP_DRIVER = r'''
import os, json
from pathlib import Path
from PySide6.QtCore import QTimer
from yt_downloader import __version__
from yt_downloader.updates.http import SecureUpdateHttpClient
from yt_downloader.app import AppController

if os.environ.get('YT_MATRIX_ASSETS'):
    assets = Path(os.environ['YT_MATRIX_ASSETS'])
    class Stream:
        def __init__(self, path): self.handle = path.open('rb')
        def iter_content(self, size):
            while True:
                chunk = self.handle.read(size)
                if not chunk: return
                yield chunk
        def close(self): self.handle.close()
    def get_json(self, url):
        payload = json.loads((assets/'release.json').read_text())
        return payload if url.endswith('/latest') else [payload]
    def stream(self, url, timeout):
        from urllib.parse import urlsplit
        name = Path(urlsplit(url).path).name
        if name not in {os.environ['YT_MATRIX_PACKAGE'], 'update-manifest.json', 'update-manifest.sig'}:
            raise ValueError('Unexpected test transport asset')
        return Stream(assets/name)
    SecureUpdateHttpClient.get_json = get_json
    SecureUpdateHttpClient.open_stream = stream

original_init = AppController.__init__
def instrumented_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    output = os.environ.get('YT_MATRIX_OBSERVATIONS')
    if not output: return
    output = Path(output); output.mkdir(exist_ok=True)
    def record(kind, value):
        with (output/(kind+'-'+__version__+'.jsonl')).open('a',encoding='utf-8') as f:
            f.write(json.dumps(value,ensure_ascii=False)+'\n')
    def capture():
        visible = self.window.isVisible()
        self.window.grab().save(str(output/('gui-'+__version__+'.png')))
        record('gui', dict(version=__version__,visible=visible))
    QTimer.singleShot(1200, capture)
    if __version__ != os.environ.get('YT_MATRIX_SOURCE'): return
    self.updates.state_changed.connect(lambda state: record('state', str(getattr(state,'value',state))))
    self.updates.failed.connect(lambda error,*a: record('failure',dict(code=error.code,message=error.user_message)))
    self.updates.update_available.connect(lambda *a: QTimer.singleShot(0,self.updates.download))
    self.updates.ready.connect(lambda *a: QTimer.singleShot(1500,self._request_update_install))
    QTimer.singleShot(1400,lambda:self.updates.check(manual=True))
AppController.__init__ = instrumented_init
'''


def run(command, cwd, log, *, env=None, timeout=600):
    with log.open('wb') as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                timeout=timeout, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError(f'{log.name}: exit {result.returncode}; inspect retained diagnostic log')


def export_source(repo, root, ref):
    root.mkdir()
    if ref:
        payload = subprocess.check_output(['git','archive','--format=zip',ref],cwd=repo)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            archive.extractall(root)  # Git-generated archive of our own tracked source.
        commit = subprocess.check_output(['git','rev-parse',ref+'^{commit}'],cwd=repo,text=True).strip()
    else:
        paths = subprocess.check_output(['git','ls-files','-z'],cwd=repo).decode().split('\0')
        paths += subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z','src'],cwd=repo).decode().split('\0')
        for name in filter(None,paths):
            source = repo/name
            if source.is_file():
                destination=root/name; destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,destination)
        commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    digest=hashlib.sha256()
    for path in sorted((root/'src').rglob('*.py')):
        digest.update(path.relative_to(root).as_posix().encode());digest.update(path.read_bytes())
    return dict(commit=commit,source_sha256=digest.hexdigest(),ref=ref or 'working-source')


def build(repo, work, version, public):
    area=work/version; area.mkdir()
    source=area/'source'
    provenance=export_source(repo,source,'v'+version if version in {'0.4.1','0.4.2'} else None)
    if version not in {'0.4.1','0.4.2'}:
        version_file=source/'src/yt_downloader/__init__.py'
        import re
        content=version_file.read_text(encoding='utf-8')
        content=re.sub(r'__version__\s*=\s*[\'\"][^\'\"]+[\'\"]',f'__version__ = "{version}"',content)
        version_file.write_text(content,encoding='utf-8')
    for relative in ('vendor/tools/ffmpeg/ffmpeg.exe','vendor/tools/ffmpeg/ffprobe.exe','vendor/tools/deno/deno.exe'):
        destination=source/relative; destination.parent.mkdir(parents=True,exist_ok=True)
        if not destination.exists():
            shutil.copy2(repo/relative,destination)
    trust=area/'test-trust-hook.py'
    trust.write_text("from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS\n"
                     f"PRODUCTION_TRUSTED_KEYS['test-matrix'] = bytes.fromhex('{public.hex()}')\n",encoding='utf-8')
    driver=area/'test-driver-hook.py';driver.write_text(APP_DRIVER,encoding='utf-8')
    environment=os.environ.copy()
    environment['PYINSTALLER_CONFIG_DIR']=str(area/'cache')
    for spec_name,label in (('YTDownloader.spec','app'),('YTDownloaderUpdater.spec','helper')):
        spec=(source/spec_name).read_text(encoding='utf-8')
        hooks=[str(trust),str(driver)] if label=='app' else [str(trust)]
        spec=spec.replace('root = Path(SPEC).resolve().parent',f'root = Path({str(source)!r})')
        spec=spec.replace('runtime_hooks=[],',f'runtime_hooks={hooks!r},')
        spec_path=area/spec_name;spec_path.write_text(spec,encoding='utf-8')
        # Remove editable checkout imports in this build process, then select
        # exactly the exported tag/source tree for Analysis and imported hooks.
        program="import sys,runpy;sys.path=[p for p in sys.path if p.lower()!=sys.argv[1].lower()];sys.path.insert(0,sys.argv[2]);sys.argv=['pyinstaller',*sys.argv[3:]];runpy.run_module('PyInstaller',run_name='__main__')"
        command=[sys.executable,'-I','-c',program,str(repo/'src'),str(source/'src'),
                 '--noconfirm','--clean','--workpath',str(area/('build-'+label)),
                 '--distpath',str(area/('dist-'+label)),str(spec_path)]
        print(f'Building {version} {label}',flush=True)
        run(command,source,area/(label+'.log'),env=environment,timeout=900)
    root=area/'dist-app/YTDownloader'
    layout='legacy-root' if version in {'0.4.1','0.4.2'} else 'internal-v1'
    helper=root/('YTDownloaderUpdater.exe' if layout=='legacy-root' else '_internal/updater/YTDownloaderUpdater.exe')
    helper.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(area/'dist-helper/YTDownloaderUpdater.exe',helper)
    info=dict(app_version=version,source_commit=provenance['commit'],validation_only=False,test_update_build=True)
    if version!='0.4.1':
        info.update(helper_layout=layout,updater_version=version,updater_protocol=1 if layout=='legacy-root' else 2,
                    supported_update_protocols=[1,2] if layout=='legacy-root' else [2])
    (root/'BUILD-INFO.json').write_text(json.dumps(info),encoding='utf-8')
    sums=[dict(Path=p.relative_to(root).as_posix(),SHA256=Archive.file_hash(p)) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json']
    (root/'SHA256SUMS.json').write_text(json.dumps(sums),encoding='utf-8')
    Archive.validate_tree(root,expected_version=version)
    (area/'source-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    return root


def assets(root, version, key, output):
    output.mkdir()
    package=output/f'YTDownloader-{version}-win64.zip'
    with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file():archive.write(path,'YTDownloader/'+path.relative_to(root).as_posix())
    base=f'https://github.com/kekaodeni/YTDownloader/releases/download/v{version}/'
    page=f'https://github.com/kekaodeni/YTDownloader/releases/tag/v{version}'
    schema=1 if version=='0.4.2' else 2
    payload=dict(schema_version=schema,app_id='YTDownloader',channel='stable',platform='windows',architecture='x64',
                 version=version,published_at='2026-09-20T00:00:00Z',minimum_auto_update_version='0.4.1' if schema==1 else '0.4.2',
                 updater_protocol=schema,key_id='test-matrix',notes={'zh-CN':'隔离冻结验收','en':'Isolated frozen acceptance'},
                 release_url=page,package=dict(name=package.name,url=base+package.name,compressed_size=package.stat().st_size,
                 extracted_size=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),sha256=Archive.file_hash(package)))
    if schema==2:
        payload.update(minimum_updater_version='0.4.2',helper_layout='internal-v1');payload['package']['kind']='standard'
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    (output/'update-manifest.json').write_bytes(raw)
    (output/'update-manifest.sig').write_bytes(base64.b64encode(key.sign(raw)))
    release=dict(tag_name='v'+version,draft=False,prerelease=False,html_url=page,
                 assets=[dict(name=name,browser_download_url=base+name) for name in ('update-manifest.json','update-manifest.sig',package.name)])
    (output/'release.json').write_text(json.dumps(release),encoding='utf-8')
    return package


def owned_processes(root):
    command = "Get-Process YTDownloader,YTDownloaderUpdater,ffmpeg,ffprobe,deno -ErrorAction SilentlyContinue | Select-Object Id,Path | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,
                            creationflags=0x08000000)
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    rows = rows if isinstance(rows,list) else [rows]
    return [row for row in rows if row.get('Path') and Path(row['Path']).resolve().is_relative_to(root.resolve())]


def stop_owned(root):
    from yt_downloader.updates.processes import process_identity, stop_recorded_process
    for row in owned_processes(root):
        identity=process_identity(row['Id'])
        if identity and Path(identity['executable']).resolve().is_relative_to(root.resolve()):
            stop_recorded_process(identity,Path(row['Path']))
    deadline=time.monotonic()+10
    while owned_processes(root) and time.monotonic()<deadline:time.sleep(0.1)
    if owned_processes(root):raise RuntimeError('Owned frozen processes did not exit')


def exercise(work, current, target):
    from yt_downloader.services.history_service import HistoryRepository
    from yt_downloader.core.models import HistoryRecord, TaskStatus
    area=work/f'chain-{current}-{target}';area.mkdir()
    install=area/'app';shutil.copytree(work/current/'dist-app/YTDownloader',install)
    data=area/'data';data.mkdir()
    videos=area/'videos';videos.mkdir()
    settings=dict(schema_version=4,download_directory=str(videos),theme='light',auto_check_updates=False)
    (data/'settings.json').write_text(json.dumps(settings),encoding='utf-8')
    # Use the real original repository initializer, keeping v0.4.x database
    # shape until the target application performs its own startup migration.
    import types
    old_source=work/'0.4.1/source/src/yt_downloader/services/history_service.py'
    module=types.ModuleType('matrix_legacy_history');sys.modules[module.__name__]=module
    exec(compile(old_source.read_bytes(),str(old_source),'exec'),module.__dict__)
    old=module.HistoryRepository(data/'history.db')
    old.upsert(HistoryRecord('preserve','fixture','https://example.org/media','保留历史',videos/'saved.mp4',
                            '720p',1,None,TaskStatus.COMPLETED,'2026-09-01T00:00:00Z'))
    observations=area/'observations';observations.mkdir()
    environment=dict(os.environ,YT_DOWNLOADER_DATA_DIR=str(data),YT_DOWNLOADER_VIDEOS_DIR=str(videos),
                     YT_MATRIX_ASSETS=str(work/('assets-'+target)),YT_MATRIX_SOURCE=current,
                     YT_MATRIX_PACKAGE=f'YTDownloader-{target}-win64.zip',YT_MATRIX_OBSERVATIONS=str(observations),
                     PYINSTALLER_RESET_ENVIRONMENT='1')
    environment.pop('YT_DOWNLOADER_UPDATE_HEALTH_SMOKE_EXIT',None)
    print(f'Exercising frozen {current} -> {target}',flush=True)
    diagnostic=(area/'process-output.log').open('wb')
    process=subprocess.Popen([str(install/'YTDownloader.exe')],cwd=install,env=environment,
                             stdout=diagnostic,stderr=subprocess.STDOUT,creationflags=0x08000000)
    deadline=time.monotonic()+240
    journal=None
    try:
        while time.monotonic()<deadline:
            paths=list((data/'update-staging').glob('update-*/update-transaction.json'))
            # Opening a live journal can deny the old helper's Windows atomic
            # replacement. Observe processes first; read only after it exits.
            helpers=[row for row in owned_processes(area)
                     if Path(row['Path']).name.lower()=='ytdownloaderupdater.exe']
            if paths and not helpers and process.poll() is not None:
                journal=json.loads(paths[0].read_text(encoding='utf-8'))
                if journal['stage'] in {'ROLLED_BACK','ROLLBACK_FAILED'}:
                    raise RuntimeError('Frozen transaction rolled back: '+journal.get('error',''))
                if journal['stage']=='COMMITTED' and (observations/f'gui-{target}.jsonl').exists():break
            failures=list(observations.glob('failure-*.jsonl'))
            if failures:raise RuntimeError('Frozen client reported failure; inspect observation report')
            time.sleep(0.25)
        if not journal or journal['stage']!='COMMITTED':
            raise TimeoutError('Frozen bridge did not commit within the acceptance deadline')
        Archive.validate_tree(install,expected_version=target)
        marker=json.loads(Path(journal['health_marker']).read_text(encoding='utf-8'))
        assert marker==dict(status='ok',transaction_id=journal['transaction_id'],app_version=target)
        visible=json.loads((observations/f'gui-{target}.jsonl').read_text(encoding='utf-8').splitlines()[-1])
        assert visible==dict(version=target,visible=True)
        saved=json.loads((data/'settings.json').read_text(encoding='utf-8'))
        assert saved==settings
        assert HistoryRepository(data/'history.db').get('preserve').title=='保留历史'
        assert Path(journal['backup_dir']).is_dir()
        if target>='0.5.0':assert not (install/'YTDownloaderUpdater.exe').exists()
        result=dict(source=current,target=target,transaction='COMMITTED',health=True,gui_visible=True,
                    user_data_preserved=True,test_key_only=True,transport='local',package_sha256=Archive.file_hash(work/('assets-'+target)/f'YTDownloader-{target}-win64.zip'))
    finally:
        stop_owned(area)
        if process.poll() is None:process.wait(timeout=10)
        diagnostic.close()
    result['orphan_processes']=False
    (area/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    return result


def direct_acceptance(work, version='0.5.0'):
    """D/E: real internal-layout extraction, startup and inert invalid helper."""
    area=work/('direct-'+version); area.mkdir()
    package=work/('assets-'+version)/f'YTDownloader-{version}-win64.zip'
    metadata=json.loads((package.parent/'update-manifest.json').read_text(encoding='utf-8'))
    root=area/'app'
    Archive().extract(package,root,signed_extracted_size=metadata['package']['extracted_size'],
                      expected_version=version)
    assert not (root/'YTDownloaderUpdater.exe').exists()
    helper=root/'_internal/updater/YTDownloaderUpdater.exe'
    assert helper.is_file()
    data=area/'data';data.mkdir()
    sentinel=data/'preserved.txt';sentinel.write_text('independent acceptance fixture')
    before={p.relative_to(data).as_posix():Archive.file_hash(p) for p in data.rglob('*') if p.is_file()}
    environment=dict(os.environ,YT_DOWNLOADER_DATA_DIR=str(data),
                     YT_DOWNLOADER_VIDEOS_DIR=str(area/'videos'),PYINSTALLER_RESET_ENVIRONMENT='1')
    for name in ('YT_MATRIX_ASSETS','YT_MATRIX_SOURCE','YT_MATRIX_OBSERVATIONS'):
        environment.pop(name,None)
    result=subprocess.run([str(helper)],cwd=root,env=environment,capture_output=True,timeout=30,
                          creationflags=0x08000000)
    assert result.returncode!=0
    Archive.validate_tree(root,expected_version=version)
    assert before=={p.relative_to(data).as_posix():Archive.file_hash(p) for p in data.rglob('*') if p.is_file()}
    for argument in ('--self-test','--smoke-test','--metadata-process-self-test'):
        run([str(root/'YTDownloader.exe'),argument],root,area/(argument[2:]+'.log'),env=environment)
    health=area/'update-direct/startup-health.json';health.parent.mkdir()
    environment['YT_DOWNLOADER_UPDATE_HEALTH_SMOKE_EXIT']='1'
    run([str(root/'YTDownloader.exe'),'--update-health-check','update-direct',str(health)],
        root,area/'health.log',env=environment)
    assert json.loads(health.read_text())==dict(status='ok',transaction_id='update-direct',app_version=version)
    assert not owned_processes(area)
    report=dict(version=version,package_sha256=Archive.file_hash(package),root_helper_absent=True,
                internal_helper=True,self_test=True,metadata_helper=True,gui_smoke=True,startup_health=True,
                invalid_helper_inert=True,test_key_only=True)
    (area/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


def interrupted_recovery(work, keyring):
    """Kill a real installer after backup, then enter recovery via the frozen app."""
    from yt_downloader.updates.installation import InstallRequest, prepare
    from yt_downloader.updates.processes import process_identity, stop_recorded_process
    area=work/'interrupted-recovery';area.mkdir()
    install=area/'app';shutil.copytree(work/'0.5.0/dist-app/YTDownloader',install)
    data=area/'data';data.mkdir()
    settings=data/'settings.json'
    settings.write_text(json.dumps(dict(schema_version=4,download_directory=str(area/'videos'),
                                        auto_check_updates=False,theme='dark')))
    from yt_downloader.services.history_service import HistoryRepository
    HistoryRepository(data/'history.db')
    before={name:Archive.file_hash(data/name) for name in ('settings.json','history.db')}
    transaction=data/'update-staging/update-frozen-interruption';transaction.mkdir(parents=True)
    for name in ('update-manifest.json','update-manifest.sig','YTDownloader-0.5.1-win64.zip'):
        shutil.copy2(work/'assets-0.5.1'/name,transaction/name)
    # A real, already exited process supplies the original PID. The real helper
    # still executes its normal Windows process wait.
    original=subprocess.Popen([sys.executable,'-c','pass']);original.wait()
    request=InstallRequest(transaction,install,data,'0.5.0','0.5.1',original.pid)
    command=prepare(request,keyring)
    environment=dict(os.environ,YT_DOWNLOADER_DATA_DIR=str(data),
                     YT_DOWNLOADER_VIDEOS_DIR=str(area/'videos'),PYINSTALLER_RESET_ENVIRONMENT='1',
                     YT_MATRIX_OBSERVATIONS=str(area/'observations'))
    for name in ('YT_MATRIX_ASSETS','YT_MATRIX_SOURCE','YT_DOWNLOADER_UPDATE_HEALTH_SMOKE_EXIT'):
        environment.pop(name,None)
    backup=area/f'.app.backup-{transaction.name}'
    with (area/'installer.log').open('wb') as output:
        helper=subprocess.Popen(command,cwd=transaction,env=environment,stdout=output,
                                stderr=subprocess.STDOUT,creationflags=0x08000000)
        deadline=time.monotonic()+180
        while not backup.exists():
            if helper.poll() is not None:raise RuntimeError('Installer exited before interruption point')
            if time.monotonic()>deadline:raise TimeoutError('No backup switch observed')
            time.sleep(.002)
        # Fault injection is external process termination, not a modified
        # transaction/health implementation or manufactured receipt.
        for row in owned_processes(area):
            if Path(row['Path']).name.lower()=='ytdownloaderupdater.exe':
                identity=process_identity(row['Id'])
                if identity:stop_recorded_process(identity,Path(row['Path']))
        stop_owned(area)
    journal=json.loads((transaction/'update-transaction.json').read_text())
    assert journal['stage'] not in {'COMMITTED','ROLLED_BACK'}
    assert install.is_dir(), 'Interruption hit the directory gap; use the staged recovery entry'
    Archive.validate_tree(install,expected_version='0.5.1')
    with (area/'recovery.log').open('wb') as output:
        app=subprocess.Popen([str(install/'YTDownloader.exe')],cwd=install,env=environment,
                             stdout=output,stderr=subprocess.STDOUT,creationflags=0x08000000)
        deadline=time.monotonic()+180
        try:
            result_path=transaction/'recovery-result.json'
            while not (area/'observations/gui-0.5.0.jsonl').exists():
                if time.monotonic()>deadline:raise TimeoutError('Frozen recovery did not relaunch the previous GUI')
                if result_path.exists() and json.loads(result_path.read_text()).get('status')=='failed':
                    raise RuntimeError('Frozen recovery reported failure')
                time.sleep(.25)
            stop_owned(area)
            final=json.loads((transaction/'update-transaction.json').read_text())
            assert final['stage']=='ROLLED_BACK'
            Archive.validate_tree(install,expected_version='0.5.0')
            assert before=={name:Archive.file_hash(data/name) for name in before}
        finally:
            stop_owned(area)
    report=dict(interruption_stage=journal['stage'],recovery='ROLLED_BACK',gui_relaunched=True,
                user_data_preserved=True,orphan_processes=False,test_key_only=True)
    (area/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--exercise-only',action='store_true')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1];work=args.work.resolve()
    if work.is_relative_to(repo): raise ValueError('Matrix workspace must be outside the checkout')
    if args.exercise_only:
        results=[exercise(work,a,b) for a,b in [('0.4.1','0.4.2'),('0.4.2','0.5.0'),('0.5.0','0.5.1')]]
        (work/'matrix-result.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        return 0
    work.mkdir(parents=True,exist_ok=False)
    # A reproducible, deliberately non-production test key for this unique work
    # directory; no production private key is read.
    key=Ed25519PrivateKey.from_private_bytes(hashlib.sha256(('test-only:'+str(work)).encode()).digest())
    public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    for version in ('0.4.1','0.4.2','0.5.0','0.5.1'):
        root=build(repo,work,version,public)
        if version!='0.4.1':assets(root,version,key,work/('assets-'+version))
    print(json.dumps(dict(builds='complete',test_key_only=True)),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())

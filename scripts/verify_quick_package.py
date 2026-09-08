"""Check frozen entrypoints and previews using exclusively isolated app data."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess

from yt_downloader.core.models import AppSettings

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--history-media',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    data=args.output/'app-data';data.mkdir(exist_ok=True)
    settings=asdict(AppSettings(download_directory=str(args.output/'Videos'),auto_check_updates=False))
    settings['codec_preference']=settings['codec_preference'].value
    (data/'settings.json').write_text(json.dumps(settings),encoding='utf-8')
    if args.history_media:
        from yt_downloader.services.history_service import HistoryRepository
        from yt_downloader.core.models import HistoryRecord, TaskStatus
        media=args.history_media.resolve()
        HistoryRepository(data/'history.db').upsert(HistoryRecord('package-preview','local-preview','https://example.invalid',
            '界面验证样例',media,'1080p',media.stat().st_size,None,TaskStatus.COMPLETED,'2026-09-06'))
    env=dict(os.environ,YT_DOWNLOADER_DATA_DIR=str(data.resolve()),YT_DOWNLOADER_VIDEOS_DIR=str((args.output/'Videos').resolve()))
    results=[]
    def run(name,arguments,timeout=30):
        process=subprocess.run([str(args.exe.resolve()),*arguments],env=env,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode:raise RuntimeError(f'{name} failed: {process.returncode}')
        results.append(dict(check=name,exit_code=process.returncode))
        print(name,'OK',flush=True)
    for theme in ('light','dark'):
        for page in ('download','download-demo','history','settings','about'):
            image=args.output/f'frozen-{page}-{theme}.png'
            run(f'{page}-{theme}',['--theme',theme,'--preview-page',page,'--render-preview',str(image.resolve())])
            if not image.is_file() or image.stat().st_size<1000:raise RuntimeError('Missing rendered preview')
    env['YT_DOWNLOADER_UPDATE_HEALTH_SMOKE_EXIT']='1'
    marker=args.output/'update-ui-health'/'startup-health.json'
    run('update-health',['--update-health-check','quick-ui-validation',str(marker.resolve())])
    health=json.loads(marker.read_text(encoding='utf-8'))
    assert health==dict(status='ok',transaction_id='quick-ui-validation',app_version='0.4.0')
    log=(data/'logs'/'yt-downloader.log').read_text(encoding='utf-8') if (data/'logs'/'yt-downloader.log').exists() else ''
    assert 'QML:' not in log, log
    if args.history_media:
        assert list((data/'cache'/'history-previews').glob('*.jpg')), 'Frozen history cover cache was not created'
        results.append(dict(check='history-video-thumbnail',exit_code=0))
    report=dict(results=results,health=health,exe_sha256=hashlib.sha256(args.exe.read_bytes()).hexdigest(),qml_warnings=[])
    (args.output/'package-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0

if __name__=='__main__':raise SystemExit(main())

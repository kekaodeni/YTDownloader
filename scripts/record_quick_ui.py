"""Capture only the demonstration application window, using local fixture data."""
from pathlib import Path
import argparse
import json
import subprocess
import threading
import queue
import time
from dataclasses import replace
from PySide6.QtCore import QObject, QTimer, QCoreApplication, QPointF, QPoint, Qt
from PySide6.QtGui import QWheelEvent, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yt_downloader.core.models import AppSettings, DownloadRequest, DownloadProgress, TaskStatus, HistoryRecord, DownloadResult
from yt_downloader.core.errors import AppError
from yt_downloader.ui.quick_window import MainWindow
from yt_downloader.ui.quick_dialogs import ErrorSession, UpdateSession
from yt_downloader.updates.models import UpdateManifest, UpdatePackage, UpdateCapability, UpdateState, UpdateProgress
from semver import Version
from verify_quick_ui import sample_video

def find(window, name):
    candidate=window.root.findChild(QObject,name)
    if candidate is not None:return candidate
    pending=[window.root.contentItem()]
    while pending:
        candidate=pending.pop()
        if candidate.objectName()==name:return candidate
        pending.extend(candidate.childItems())
    raise LookupError(name)

def wheel(window, name, angle):
    item=find(window,name)
    point=item.mapToScene(QPointF(item.width()/2,item.height()/2))
    event=QWheelEvent(point,QPointF(window.root.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,angle),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
    QCoreApplication.sendEvent(window.root,event)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--portrait-media',type=Path)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    window=MainWindow(AppSettings(download_directory='D:/Videos',auto_check_updates=False),ytdlp_version='2026.8.19',ffmpeg_description='随软件提供')
    window.root.setTitle('YTDownloader UI Preview')
    window.root.setPosition(140,60)
    window.show();window.root.raise_();window.root.requestActivate()
    video=sample_video()
    request=DownloadRequest('demo-task',video,video.formats[0],Path('D:/Videos'),video.title)
    records=[HistoryRecord(f'h-{i}',video.video_id,video.url,video.title+f' · {i+1}',Path('D:/Videos/example.mp4'),'1080p',100_000_000,None,TaskStatus.COMPLETED,'2026-09-05 09:00') for i in range(100)]
    if args.portrait_media:
        from yt_downloader.services.ffmpeg_service import FfmpegService
        service=FfmpegService()
        records[0]=replace(records[0],file_path=args.portrait_media.resolve())
        window.history_page.configure_thumbnails(service,args.output.parent/'recording-history-cache')
    window.history_page.set_records(records)
    process=None
    frames=queue.Queue(maxsize=3)
    capture=QTimer()
    capture.setTimerType(Qt.PreciseTimer)
    capture.setInterval(16)
    captured=0
    output_frames=0
    recorder_started=0
    def capture_frame():
        nonlocal captured
        if frames.full():return
        window.root.update()
        frame=window.grab().convertToFormat(QImage.Format_RGBA8888)
        if frame.isNull():return
        frames.put((time.perf_counter()-recorder_started,bytes(frame.constBits())))
        captured+=1
    capture.timeout.connect(capture_frame)
    def encode():
        nonlocal output_frames
        previous=None
        while True:
            entry=frames.get()
            if entry is None:break
            timestamp,data=entry
            target=int(timestamp*60)
            if previous is not None:
                while output_frames<target:
                    process.stdin.write(previous);output_frames+=1
            process.stdin.write(data);output_frames+=1
            previous=data
        process.stdin.close()
    encoder=None
    log=args.output.with_suffix('.ffmpeg.log').open('w',encoding='utf-8')
    def steps():
        nonlocal process, recorder_started, encoder
        yield 500
        size=window.grab().size()
        process=subprocess.Popen([str(Path('vendor/tools/ffmpeg/ffmpeg.exe').resolve()),'-hide_banner','-y','-f','rawvideo','-pixel_format','rgba','-video_size',f'{size.width()}x{size.height()}','-framerate','60','-i','pipe:0','-vf','scale=1200:-2','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(args.output.resolve())],stdin=subprocess.PIPE,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        recorder_started=time.perf_counter()
        encoder=threading.Thread(target=encode,daemon=True);encoder.start()
        capture.start()
        yield 1200
        window.download_page.set_url(video.url)
        window.download_page.show_video(video);window.download_page.add_task(request)
        window.download_page.update_task(DownloadProgress(request.task_id,TaskStatus.DOWNLOADING_VIDEO,31,31_000_000,100_000_000,8_700_000,8))
        yield 1700
        window._select_page(1);yield 1000
        window.history_page.select('h-0')
        find(window,'historyList').forceActiveFocus()
        QTest.keyClick(window.root,Qt.Key_F10,Qt.ShiftModifier);yield 1500
        QTest.keyClick(window.root,Qt.Key_Escape);yield 250
        if args.portrait_media:
            from yt_downloader.ui.quick_cover import CoverSession
            cover=CoverSession(args.portrait_media.resolve(),'recorded-portrait',args.output.parent/'recording-previews',service,window)
            cover.show()
            for _ in range(50):
                if cover.state['previewEnabled']:break
                yield 100
            cover.generatePreview()
            for _ in range(50):
                if cover.state['applyEnabled']:break
                yield 100
            assert cover.state['applyEnabled']
            yield 1800
            cover.reject();yield 300
        for _ in range(8):wheel(window,'historyList',-120);yield 80
        for _ in range(5):wheel(window,'historyList',120);yield 80
        yield 600
        window.history_page.manage(True);window.history_page.selectAll(True);yield 700
        window.history_page.manage(False);window._select_page(2);yield 900
        for _ in range(7):wheel(window,'settingsScroll',-120);yield 85
        window.theme.set_mode('dark');yield 1200
        window._select_page(3);yield 1000
        for page in (0,1,3,2,0):window._select_page(page);yield 85
        yield 700
        window.download_page.update_task(DownloadProgress(request.task_id,TaskStatus.DOWNLOADING_VIDEO,67,67_000_000,100_000_000,8_700_000,4));yield 700
        window.download_page.cancel_task(request.task_id);yield 500
        window.download_page.fail_task(request.task_id,TaskStatus.CANCELLED);yield 700
        next_request=replace(request,task_id='demo-next')
        window.download_page.add_task(next_request);window.download_page.task_started(next_request.task_id);yield 500
        window.download_page.complete_task(DownloadResult(next_request.task_id,Path('D:/Videos/example.mp4'),100_000_000,'now'));yield 700
        error=ErrorSession(AppError('preview','这是离线界面演示中的错误提示，可以重试。','Redacted preview details'),'Preview report',window,retry_callback=lambda:None)
        error.show();yield 1000;error.reject();yield 500
        manifest=UpdateManifest(Version.parse('0.4.1'),'2026-09-05',Version.parse('0.4.0'),1,'preview','离线更新界面演示','Offline UI preview','https://example.invalid/release',UpdatePackage('preview.zip','https://example.invalid/preview.zip',100,200,'0'*64))
        update=UpdateSession(manifest,UpdateCapability.DOWNLOAD_AND_VERIFY,window)
        update.show();update.set_state(UpdateState.DOWNLOADING);update.set_progress(UpdateProgress(35,100));yield 900
        update.set_state(UpdateState.READY_TO_INSTALL);yield 900;update.reject();yield 500
        window.theme.set_mode('light');yield 900
        if process.poll() is not None:raise RuntimeError('Recording failed: '+str(args.output.with_suffix('.ffmpeg.log')))
        capture.stop()
        yield 100
        (args.output.with_suffix('.json')).write_text(json.dumps(dict(qml_warnings=window.qml_warnings,fixture_data=True,recording_fps=60,captured_frames=captured,source="QQuickWindow.grabWindow; excludes all other windows"),ensure_ascii=False,indent=2),encoding='utf-8')
        app.quit()
    iterator=steps()
    def advance():
        try:delay=next(iterator)
        except StopIteration:return
        except BaseException:
            import traceback
            traceback.print_exc();app.exit(2);return
        QTimer.singleShot(delay,advance)
    QTimer.singleShot(0,advance)
    result=app.exec()
    capture.stop()
    if encoder:
        frames.put(None)
        encoder.join(timeout=20)
    if process:
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        if process.returncode:result=2
    log.close();window.dispose()
    return result

if __name__=='__main__':raise SystemExit(main())

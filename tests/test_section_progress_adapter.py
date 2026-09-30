from dataclasses import replace
import json
from pathlib import Path
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest

from test_download_service import _request
from yt_downloader.core.models import TaskStatus
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL


def test_section_time_is_progress_and_media_speed_drives_eta(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter
    request = replace(_request(tmp_path), clip_enabled=True, clip_start=8, clip_end=108)
    events = []
    now = [0.0]
    adapter = SectionDownloadProgressAdapter(request, events.append, clock=lambda: now[0])
    adapter.started()
    assert events[-1].status == TaskStatus.DOWNLOADING_VIDEO
    assert events[-1].percent == 0
    now[0] = .5
    for line in ('out_time_us=25000000', 'total_size=1000', 'speed=1.5x', 'progress=continue'):
        adapter.feed(line)
    event = events[-1]
    assert event.percent == 25
    assert event.eta == 50
    assert event.downloaded_bytes == 1000
    assert event.total_bytes is None  # no invented exact total


@pytest.mark.parametrize('seconds,percent', [(25,25), (50,50), (100,100), (120,100)])
def test_section_progress_units_and_bounds(tmp_path, seconds, percent):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter
    request = replace(_request(tmp_path), clip_enabled=True, clip_end=100)
    events = []
    adapter = SectionDownloadProgressAdapter(request, events.append)
    adapter.feed(f'out_time_ms={seconds * 1000000}')
    adapter.feed('progress=continue')
    assert events[-1].percent == percent


def test_section_invalid_progress_never_fakes_completion(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter
    events = []
    adapter = SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_end=100), events.append)
    for bad in ('N/A', '-10', 'nan', 'inf', 'broken'):
        adapter.feed('out_time_us=' + bad)
        adapter.feed('progress=end')
    assert events == []
    adapter.feed('out_time=00:00:50.000000')
    adapter.feed('speed=N/A')
    adapter.feed('total_size=N/A')
    adapter.feed('progress=continue')
    assert events[-1].percent == 50
    assert events[-1].eta is None and events[-1].downloaded_bytes is None


def test_section_metadata_size_stays_an_estimate(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter
    events = []
    adapter = SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_start=8, clip_end=29), events.append)
    adapter.started()
    assert events[-1].total_bytes == 150
    assert events[-1].total_is_estimate


def test_section_stat_fallback_and_ui_cadence(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter
    now = [0.0]
    events = []
    adapter = SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_end=100), events.append,
                                             clock=lambda: now[0])
    adapter.output_path = tmp_path / 'native.part'
    adapter.output_path.write_bytes(b'x' * 1000)
    adapter.feed('out_time_us=25000000')
    adapter.feed('total_size=N/A')
    adapter.feed('progress=continue')
    assert events[-1].downloaded_bytes == 1000
    for stamp in (.1, .2, .3, .4):
        now[0] = stamp
        adapter.tick()
    assert len(events) == 1
    adapter.output_path.write_bytes(b'x' * 3000)
    now[0] = .5
    adapter.tick()
    assert len(events) == 2
    assert events[-1].downloaded_bytes == 3000
    assert events[-1].speed == 4000
    now[0] = 1
    for line in ('out_time_us=26000000', 'total_size=2500', 'speed=1.5x', 'progress=continue'):
        adapter.feed(line)
    assert events[-1].downloaded_bytes == 3000
    assert events[-1].speed == 4000  # delayed pipe data must not reset stat progress


def test_section_tick_publishes_rate_limited_media_position(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter
    now, events = [0.0], []
    adapter = SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_end=100), events.append,
                                             clock=lambda: now[0])
    adapter.started()
    now[0] = .49
    for line in ('out_time_us=25000000', 'speed=1.5x', 'progress=continue'):
        adapter.feed(line)
    assert events[-1].percent == 0
    now[0] = .5
    adapter.tick()
    assert events[-1].percent == 25 and events[-1].eta == 50


def test_section_zero_exit_with_broken_input_is_recoverable_failure(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter, observed_section_popen
    from yt_downloader.core.errors import AppError, ErrorContext
    adapter = SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_end=100), lambda p: None)
    adapter.stderr('[tls] Unable to read from socket')
    adapter.stderr('[in#0] Error during demuxing: I/O error')
    class ExitedProcess:
        def wait(self, timeout=None): return 0
        def poll(self): return 0
    process_type = observed_section_popen(ExitedProcess, adapter, threading.Event(), ErrorContext())
    process = process_type.__new__(process_type)
    process._stopping = False
    process._read_error = None
    process._job = None
    process._readers = []
    with pytest.raises(AppError, match='网络连接失败') as error:
        process.wait()
    assert error.value.code == 'NETWORK_ERROR'


def test_section_harmless_decoder_warning_does_not_fail_download(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter
    adapter = SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_end=100), lambda p: None)
    adapter.stderr('[h264] Increasing reorder buffer to 2')
    assert not adapter.input_error


def test_section_containment_failure_stops_child_and_reports_error(tmp_path, monkeypatch):
    from yt_downloader.services import section_progress
    from yt_downloader.workers.download_queue import _TaskControl
    from yt_downloader.core.errors import AppError, ErrorContext
    closed, killed = [], []
    class Job:
        def assign(self, pid): return False
        def close(self): closed.append(True)
    class Process:
        pid = 123
        def __init__(self, *args, **kwargs): pass
        def wait(self, timeout=None): return 0
        def kill(self, timeout=None):
            killed.append(True)
            self.wait(timeout)
    monkeypatch.setattr(section_progress, 'ProcessJob', Job)
    adapter = section_progress.SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_end=100), lambda p: None)
    process_type = section_progress.observed_section_popen(Process, adapter, _TaskControl(live_pause=True), ErrorContext())
    with pytest.raises(AppError) as error:
        process_type(['ffmpeg', 'output.mp4'])
    assert error.value.code == 'ffmpeg_failed'
    assert killed == closed == [True]


def test_section_resume_failure_terminates_job_without_hanging(tmp_path):
    from yt_downloader.services.section_progress import SectionDownloadProgressAdapter, observed_section_popen
    from yt_downloader.core.errors import AppError, ErrorContext
    events, stopped = [], []
    adapter = SectionDownloadProgressAdapter(replace(_request(tmp_path), clip_end=100), events.append)
    adapter.started()
    adapter.publish(replace(adapter.latest, status=TaskStatus.PAUSED))
    class Job:
        def resume(self): raise OSError('resume denied')
        def terminate(self): stopped.append('job')
    class Process:
        def wait(self, timeout=None): return 0
        def poll(self): return 0
        def kill(self, timeout=None):
            stopped.append('process')
            self.wait(timeout)
    control = threading.Event()
    control.is_paused = lambda: False
    process_type = observed_section_popen(Process, adapter, control, ErrorContext())
    process = process_type.__new__(process_type)
    process._stopping = False
    process._read_error = None
    process._suspended = True
    process._job = Job()
    process._readers = []
    with pytest.raises(AppError) as error:
        process.wait()
    assert error.value.code == 'ffmpeg_failed'
    assert stopped == ['job', 'process']
    assert events[-1].status == TaskStatus.PAUSED


def test_section_child_uses_ydl_resolved_proxy_per_input_without_changing_auth():
    from yt_downloader.services.section_network import section_process_options
    argv = ['ffmpeg', '-headers', 'Referer: https://example.org\r\n', '-cookies', 'secret cookie',
            '-ss', '8', '-t', '60', '-i', 'https://media.example/video', '-i', 'https://local.test/audio',
            '-map', '0:0', '-c', 'copy', 'output.mp4']
    proxies = {'https': 'http://127.0.0.1:8000', 'no': 'local.test'}
    child_argv, env = section_process_options(argv, {'HTTP_PROXY':'http://wrong:9'}, proxies)
    assert child_argv[child_argv.index('-headers')+1] == argv[2]
    assert child_argv[child_argv.index('-cookies')+1] == 'secret cookie'
    assert 'http://wrong:9' not in env.values()
    assert child_argv[child_argv.index('https://media.example/video')-2] == 'http://127.0.0.1:8000'
    assert child_argv[child_argv.index('https://local.test/audio')-2] == ''
    assert [v for v in child_argv if v in ('8','60','0:0','copy','output.mp4')] == ['8','60','0:0','copy','output.mp4']


def test_explicit_direct_clears_inherited_proxy_for_section():
    from yt_downloader.services.section_network import section_process_options
    args, env = section_process_options(['ffmpeg','-i','https://media.example/video','out.mp4'],
                                        {'http_proxy':'http://wrong:9','HTTPS_PROXY':'http://wrong:9'},
                                        {'all':'__noproxy__'})
    assert args[args.index('-http_proxy')+1] == ''
    assert not env


@pytest.fixture(scope='module')
def native_section_source(tmp_path_factory):
    path = tmp_path_factory.mktemp('native-section') / 'source.mp4'
    ffmpeg = Path('vendor/tools/ffmpeg/ffmpeg.exe').resolve()
    if not ffmpeg.is_file():
        pytest.skip('Bundled FFmpeg is unavailable')
    subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                    'testsrc2=size=64x64:rate=25', '-f', 'lavfi', '-i', 'sine=frequency=440',
                    '-t', '5', '-c:v', 'libx264', '-g', '25', '-c:a', 'aac', '-movflags', '+faststart', str(path)], check=True)
    subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel','error','-f','lavfi','-i','sine=frequency=440',
                    '-t','5','-c:a','libopus',str(path.with_name('audio.webm'))],check=True)
    return path


def native_factory(source):
    class FixtureYDL(ReadOnlyCookieYoutubeDL):
        def __init__(self, options):
            super().__init__({**options,
                              'external_downloader_args': {**options.get('external_downloader_args',{}),'ffmpeg_i': ['-re']}})
        def download(self, urls):
            formats=[{'format_id':'fixture', 'url':source, 'protocol':'http', 'ext':'mp4', 'vcodec':'h264', 'acodec':'aac'}]
            if isinstance(source,tuple):
                formats=[{'format_id':'fixture-video', 'url':source[0], 'protocol':'http', 'ext':'mp4', 'vcodec':'h264', 'acodec':'none'},
                         {'format_id':'fixture-audio','url':source[1], 'protocol':'http','ext':'webm','vcodec':'none','acodec':'opus'}]
            self.process_ie_result({'id':'fixture', 'title':'fixture', 'duration':5,
                                    'extractor_key':'Generic', 'webpage_url':urls[0],
                                    'formats':formats}, download=True)
            return 0
    return FixtureYDL


def section_request(tmp_path, source):
    request = _request(tmp_path)
    option = replace(request.format, format_selector='fixture', requires_merge=False,
                     video_format_id='fixture', audio_format_id='', estimated_size=source.stat().st_size)
    return replace(request, format=option, video=replace(request.video, duration=5, formats=(option,)),
                   clip_enabled=True, clip_start=1, clip_end=3)


@pytest.fixture
def native_source_url(native_section_source):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = native_section_source.with_name(self.path.lstrip('/')).read_bytes()
            start, end = 0, len(data)-1
            if self.headers.get('Range'):
                span = self.headers['Range'].removeprefix('bytes=').split('-')
                start, end = int(span[0]), int(span[1]) if span[1] else end
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
            else:
                self.send_response(200)
            self.send_header('Accept-Ranges','bytes')
            self.send_header('Content-Type','video/mp4')
            self.send_header('Content-Length',str(end-start+1))
            self.end_headers()
            self.wfile.write(data[start:end+1])
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f'http://127.0.0.1:{server.server_port}/source.mp4'
    server.shutdown()
    server.server_close()
    worker.join()


def test_native_ffmpegfd_section_updates_task_before_finished_and_preserves_output(tmp_path, native_section_source, native_source_url):
    source = native_section_source
    request = section_request(tmp_path, source)
    events = []
    result = DownloadService(ydl_factory=native_factory(native_source_url)).download(request, events.append, threading.Event())
    downloading = [p for p in events if p.status == TaskStatus.DOWNLOADING_VIDEO]
    assert downloading[0].percent == 0
    assert len(downloading) >= 3
    assert any(0 < p.percent < 100 for p in downloading)
    assert any(p.eta is not None for p in downloading)
    assert downloading[-1].percent >= 99
    assert events[-1].status == TaskStatus.COMPLETED
    terminal=[p for p in events if p.status in {TaskStatus.MERGING,TaskStatus.POST_PROCESSING}]
    assert terminal
    assert all(p.total_bytes == result.file_path.stat().st_size and not p.total_is_estimate for p in terminal)
    probe = subprocess.run(['vendor/tools/ffmpeg/ffprobe.exe', '-v','error','-show_format','-show_streams',
                            '-of','json',str(result.file_path)], capture_output=True, encoding='utf-8', check=True)
    data = json.loads(probe.stdout)
    assert 1.8 < float(data['format']['duration']) < 2.2
    assert {s['codec_type'] for s in data['streams']} == {'video','audio'}


def test_native_section_cancel_stops_child(tmp_path, native_section_source, native_source_url):
    from yt_downloader.core.errors import OperationCancelled, OperationPaused
    from yt_downloader.workers.download_queue import _TaskControl
    control = _TaskControl()
    service = DownloadService(ydl_factory=native_factory(native_source_url))
    request = section_request(tmp_path, native_section_source)
    events = []
    def progress(p):
        events.append(p)
        control.set_status(p.status)
        if p.status == TaskStatus.DOWNLOADING_VIDEO and p.percent and p.percent > 10:
            control.set()
    started = time.monotonic()
    with pytest.raises(OperationCancelled):
        service.download(request,progress,control)
    assert time.monotonic()-started < 4
    workspace = tmp_path/'.ytdownloader-tmp'
    assert not workspace.exists()


@pytest.mark.parametrize('cancel_while_paused', [False, True])
def test_native_section_queue_pauses_and_resumes_same_pid_and_file(qtbot, tmp_path, native_section_source, native_source_url, cancel_while_paused):
    from yt_downloader.workers.download_queue import DownloadQueueController
    request = replace(section_request(tmp_path, native_section_source), clip_start=0, clip_end=5)
    queue = DownloadQueueController(DownloadService(ydl_factory=native_factory(native_source_url)))
    events, completed, paused, failures = [], [], [], []
    queue.progress.connect(events.append)
    queue.completed.connect(completed.append)
    queue.paused.connect(paused.append)
    queue.failed.connect(lambda _task, error: failures.append(error))
    queue.enqueue(request)
    try:
        qtbot.waitUntil(lambda: any(p.percent and p.percent > 10 for p in events), timeout=5000)
        control = queue._active[request.task_id][3]
        pid = control.section_pid
        path = control.section_path
        assert queue.pause_task(request.task_id), [(p.status, p.percent) for p in events]
        qtbot.waitUntil(lambda: bool(paused) or bool(failures), timeout=3000)
        assert not failures, [getattr(e, 'technical_message', str(e)) for e in failures]
        assert paused == [request.task_id]
        before = events[-1].percent
        assert path.exists(), (str(path), list(tmp_path.rglob('*')), [(p.status, p.percent) for p in events], failures)
        size = path.stat().st_size
        qtbot.wait(350)
        assert path.stat().st_size == size
        assert queue.task_position(request.task_id) == 'paused'
        if cancel_while_paused:
            assert queue.cancel(request.task_id)
            qtbot.waitUntil(lambda: not queue.is_busy, timeout=5000)
            assert not path.exists()
            assert not completed
            return
        assert queue.resume_task(request.task_id)
        assert control.section_pid == pid
        assert control.section_path == path
        qtbot.waitUntil(lambda: bool(completed) and not queue.is_busy, timeout=5000)
        assert len(completed) == 1
        after = [p.percent for p in events if p.status in {TaskStatus.DOWNLOADING_VIDEO, TaskStatus.PAUSED} and p.percent is not None]
        assert after == sorted(after)
        assert before > 0
    finally:
        queue.cancel_all()
        qtbot.waitUntil(lambda: not queue.is_busy, timeout=5000)


def test_native_split_opus_section_drops_negative_preroll_without_reencoding(tmp_path, native_section_source, native_source_url):
    request=section_request(tmp_path,native_section_source)
    option=replace(request.format,format_selector='fixture-video+fixture-audio',video_format_id='fixture-video',
                   audio_format_id='fixture-audio',acodec='opus',requires_merge=True,final_ext='mkv')
    request=replace(request,format=option)
    service=DownloadService(ydl_factory=native_factory((native_source_url,native_source_url.replace('source.mp4','audio.webm'))))
    events=[]
    result=service.download(request,events.append,threading.Event())
    terminal=[p for p in events if p.status in {TaskStatus.MERGING,TaskStatus.POST_PROCESSING}]
    assert terminal
    assert all(p.total_bytes == result.file_path.stat().st_size and not p.total_is_estimate for p in terminal)
    probe=subprocess.run(['vendor/tools/ffmpeg/ffprobe.exe','-v','error','-show_format','-show_streams',
                          '-of','json',str(result.file_path)],capture_output=True,encoding='utf-8',check=True)
    data=json.loads(probe.stdout)
    assert 1.95 < float(data['format']['duration']) < 2.15
    assert {s['codec_name'] for s in data['streams']} == {'h264','opus'}
    # Stream-copy retains the codec's keyframe constraint (one second in this
    # fixture); audio must no longer add an extra second of preroll to the mux.
    audio=next(s for s in data['streams'] if s['codec_type']=='audio')
    video=next(s for s in data['streams'] if s['codec_type']=='video')
    assert abs(float(audio['start_time'])) < .03
    assert 0 <= float(video['start_time']) <= 1.05


def test_native_section_argv_preserves_headers_cookies_seek_mapping_and_copy(tmp_path,native_section_source,native_source_url,monkeypatch):
    from http.cookiejar import Cookie
    from yt_dlp.downloader import external
    base=external.Popen
    calls=[]
    class RecordedPopen(base):
        def __init__(self,args,*remaining,**kwargs):
            calls.append(list(args))
            super().__init__(args,*remaining,**kwargs)
    monkeypatch.setattr(external,'Popen',RecordedPopen)
    factory=native_factory(native_source_url)
    class AuthYDL(factory):
        def __init__(self,options):
            super().__init__(options)
            self.params['http_headers']={'User-Agent':'Fixture UA','Referer':'https://origin.example/','Origin':'https://origin.example'}
            self.cookiejar.set_cookie(Cookie(0,'test_cookie','fixture-secret',None,False,'127.0.0.1',
                                            False,False,'/',True,False,None,True,None,None,{}))
    request=section_request(tmp_path,native_section_source)
    DownloadService(ydl_factory=AuthYDL).download(request,lambda p:None,threading.Event())
    assert external.Popen is RecordedPopen  # scope restored, other tasks stay native
    assert len(calls)==1
    argv=calls[0]
    assert argv[argv.index('-i')+1]==native_source_url
    assert argv[argv.index('-ss')+1]=='1'
    assert argv[argv.index('-t')+1]=='2'
    assert argv[argv.index('-c')+1]=='copy'
    assert argv[argv.index('-progress')+1]=='pipe:1'
    assert 'Fixture UA' in argv[argv.index('-headers')+1]
    assert 'Referer: https://origin.example/' in argv[argv.index('-headers')+1]
    assert 'Origin: https://origin.example' in argv[argv.index('-headers')+1]
    assert 'test_cookie=fixture-secret' in argv[argv.index('-cookies')+1]


def test_concurrent_sections_keep_progress_and_cancellation_owned_by_each_task(tmp_path,native_section_source,native_source_url):
    from concurrent.futures import ThreadPoolExecutor
    from yt_downloader.core.errors import OperationCancelled
    from yt_dlp.downloader import external
    original=external.Popen
    service=DownloadService(ydl_factory=native_factory(native_source_url))
    first=replace(section_request(tmp_path,native_section_source),task_id='cancel-section')
    second=replace(first,task_id='keep-section')
    cancel=threading.Event()
    events_a,events_b=[],[]
    def progress(p):
        events_a.append(p)
        if p.percent and p.percent>10:
            cancel.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(service.download,first,progress,cancel)
        b=pool.submit(service.download,second,events_b.append,threading.Event())
        with pytest.raises(OperationCancelled):
            a.result(timeout=10)
        assert b.result(timeout=10).file_path.is_file()
    assert {p.task_id for p in events_a}=={'cancel-section'}
    assert {p.task_id for p in events_b}=={'keep-section'}
    assert events_b[-1].status==TaskStatus.COMPLETED
    assert external.Popen is original

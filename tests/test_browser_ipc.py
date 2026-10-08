import uuid
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtNetwork import QLocalServer
from conftest import run_frames
from yt_downloader.browser_companion.ipc_client import send_local
from yt_downloader.browser_companion.ipc_server import DesktopIPC
from yt_downloader.browser_companion.protocol import response

def test_real_windows_pipe_current_user_roundtrip_and_duplicates(qapp, tmp_path):
    name = 'YTDownloader-test-' + uuid.uuid4().hex
    server = DesktopIPC(name=name, lock_path=tmp_path / 'instance.lock')
    assert server.listen()
    assert server.server.socketOptions() & QLocalServer.SocketOption.UserAccessOption
    other = DesktopIPC(name=name, lock_path=tmp_path / 'instance.lock')
    assert not other.listen()
    calls = []
    server.set_receiver(lambda m: (calls.append(m), response(m['request_id'], 'delivered'))[1])
    message = dict(protocol=1,action='send_url',request_id='one',url='https://example.org/video')
    with ThreadPoolExecutor() as executor:
        for request in [message,message,dict(message,url='https://example.org/other')]:
            result = executor.submit(send_local, request, name=name)
            for _ in range(30):
                if result.done(): break
                run_frames(qapp, 30)
            assert result.result(timeout=2)['status'] == ('invalid_message' if request != message else 'delivered')
    assert calls == [message]
    server.close()
    assert other.listen()
    other.close()

def test_startup_queue_and_reconnect(qapp, tmp_path):
    name = 'YTDownloader-test-' + uuid.uuid4().hex
    server = DesktopIPC(name=name, lock_path=tmp_path / 'instance.lock')
    assert server.listen()
    with ThreadPoolExecutor() as executor:
        request = dict(protocol=1,action='ping',request_id='initial')
        result = executor.submit(send_local, request, name=name)
        for _ in range(30):
            if result.done(): break
            run_frames(qapp, 30)
        assert result.result(timeout=2)['status'] == 'accepted'
    delivered = []
    server.set_receiver(delivered.append)
    assert delivered == [request]
    server.close()

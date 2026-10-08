from types import SimpleNamespace
from unittest.mock import Mock
from conftest import run_frames
from yt_downloader.browser_companion.incoming import IncomingBrowserRequests
from yt_downloader.core.models import ParseState

def window():
    page = SimpleNamespace(parse_state=ParseState.RUNNING,set_url=Mock(),requestParse=Mock(),requestDownload=Mock())
    return SimpleNamespace(download_page=page,root=Mock(),_select_page=Mock(),scroll_download_to_top=Mock())

def send(receiver, url, request_id='one'):
    return receiver.receive(dict(protocol=1,action='send_url',request_id=request_id,url=url,browser='chrome'))

def test_running_parse_fifo_no_double_parse_or_download(qapp):
    target = window()
    target.root.Visibility.Minimized = 3
    target.root.visibility.return_value = 3
    receiver = IncomingBrowserRequests(target)
    assert send(receiver,'https://example.org/first')['status'] == 'delivered'
    assert send(receiver,'https://example.org/first','duplicate')['duplicate']
    send(receiver,'https://example.org/second','second')
    receiver.drain()
    target.download_page.requestParse.assert_not_called()
    target.download_page.parse_state = ParseState.IDLE
    receiver.drain()
    target.download_page.set_url.assert_called_with('https://example.org/first')
    target.download_page.parse_state = ParseState.SLOW
    receiver.drain()
    assert target.download_page.requestParse.call_count == 1
    target.download_page.parse_state = ParseState.FAILED
    receiver.drain()
    target.download_page.set_url.assert_called_with('https://example.org/second')
    assert target.download_page.requestParse.call_count == 2
    target.download_page.requestDownload.assert_not_called()
    target.root.showNormal.assert_called()
    receiver.timer.stop()

def test_repeat_url_after_short_dedup_and_bounded_queue(qapp):
    receiver = IncomingBrowserRequests(window())
    url = 'https://example.org/video'
    send(receiver,url)
    receiver.recent[url] -= 4
    assert not send(receiver,url,'two').get('duplicate')
    for index in range(14): send(receiver,f'https://example.org/{index}',str(index))
    assert send(receiver,'https://example.org/overflow','overflow')['status'] == 'busy'
    receiver.timer.stop()

def test_real_presenter_uses_existing_cookie_profile_and_parse_signal(quick_window):
    target = quick_window
    original = list(target.cookies.profiles)
    requested = []
    target.download_page.parse_requested.connect(requested.append)
    receiver = IncomingBrowserRequests(target)
    send(receiver,'https://www.youtube.com/watch?v=8kIJ7QLTSRc')
    receiver.drain()
    assert requested == ['https://www.youtube.com/watch?v=8kIJ7QLTSRc']
    assert list(target.cookies.profiles) == original
    assert target.download_page.tasks.rowCount() == 0
    receiver.timer.stop()


def test_real_window_restores_and_preserves_existing_tasks(quick_window, qapp, tmp_path):
    from pathlib import Path
    from scripts.verify_quick_ui import sample_video
    from yt_downloader.core.models import DownloadRequest
    target = quick_window
    video = sample_video()
    target.download_page.add_task(DownloadRequest('existing', video, video.formats[0],
                                                Path(tmp_path), 'existing'))
    before = target.download_page.tasks.get(0)
    target._select_page(4)
    target.root.showMinimized()
    run_frames(qapp, 60)
    receiver = IncomingBrowserRequests(target)
    send(receiver, 'https://www.bilibili.com/video/BV1pKap6JEAz/')
    assert target.root.visibility() != target.root.Visibility.Minimized
    assert target.download_page.tasks.rowCount() == 1
    assert target.download_page.tasks.get(0) == before
    receiver.timer.stop()

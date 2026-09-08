from yt_downloader.core.models import DownloadProgress, TaskStatus
from yt_downloader.ui.quick_download import TaskPresentation
from test_download_service import _request

def test_progress_bar_percent_and_speed_are_always_visible(tmp_path):
    card = TaskPresentation(_request(tmp_path))
    card.progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO))
    assert card.values['indeterminate']
    assert card.values['percentText'] == '—%'
    assert card.values['speed'] == '—'

def test_cancelling_freezes_progress_and_clears_live_metrics(tmp_path):
    card = TaskPresentation(_request(tmp_path))
    card.progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, 42, 42, 100, 2_000_000, 9))
    card.progress(DownloadProgress("x", TaskStatus.CANCELLING))
    assert card.values['statusText'] == '正在取消…'
    assert not card.values['indeterminate']
    assert card.values['percent'] == 42
    assert card.values['percentText'] == '42%'
    assert card.values['speed'] == '—'
    assert card.values['eta'] == '剩余 —'

def test_estimated_total_is_labeled_instead_of_presented_as_exact(tmp_path):
    card = TaskPresentation(_request(tmp_path))
    card.progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, 20, 50, 250, 1000, 2, total_is_estimate=True))
    assert card.values['size'] == '50 B / 估算 250 B'

def test_unknown_total_keeps_downloaded_speed_and_eta_visible(tmp_path):
    card = TaskPresentation(_request(tmp_path))
    card.progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, None, 512, None, 1024, 12))
    assert card.values['indeterminate']
    assert card.values['percentText'] == '—%'
    assert card.values['size'] == '512 B / —'
    assert card.values['speed'] == '1.0 KB/s'
    assert card.values['eta'] == '剩余 00:12'

def test_progress_switches_from_unknown_to_determinate_without_reset(tmp_path):
    card = TaskPresentation(_request(tmp_path))
    card.progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, None, 100, None, 50, None))
    card.progress(DownloadProgress("x", TaskStatus.DOWNLOADING_VIDEO, 20, 200, 1000, 50, 16))
    assert not card.values['indeterminate']
    assert card.values['percent'] == 20
    assert card.values['percentText'] == '20%'

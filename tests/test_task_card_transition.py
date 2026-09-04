from dataclasses import replace

from PySide6.QtCore import QTimer

from test_download_service import _request
from yt_downloader.core.models import DownloadResult
from yt_downloader.ui.motion import MotionManager
from yt_downloader.ui.pages.download_page import DownloadPage


def test_new_running_card_and_terminal_retirement_commit_one_layout_change(qapp, qtbot, tmp_path, monkeypatch):
    motion = MotionManager()
    page = DownloadPage(str(tmp_path), motion=motion)
    qtbot.addWidget(page)
    page.show()
    first = replace(_request(tmp_path), task_id='old-terminal')
    second = replace(_request(tmp_path), task_id='new-running')
    page.add_task(first)
    qapp.processEvents()
    page.complete_task(DownloadResult(first.task_id, tmp_path / 'old.mp4', 10, 'now'))
    calls = []
    original = motion.transition_layout
    monkeypatch.setattr(motion, 'transition_layout', lambda host, mutation: (calls.append(host), original(host, mutation))[1])

    page.add_task(second)
    assert page.task_layout.indexOf(page.cards[second.task_id]) == -1
    page.task_started(second.task_id)

    assert len(calls) == 1
    assert set(page.cards) == {second.task_id}
    assert page.task_layout.indexOf(page.cards[second.task_id]) >= 0

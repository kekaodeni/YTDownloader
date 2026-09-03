from dataclasses import replace
from types import SimpleNamespace

from test_download_service import _request
from yt_downloader.app import AppController
from yt_downloader.workers.request_gate import LatestRequestGate


def test_only_the_latest_metadata_generation_can_update_the_ui() -> None:
    gate = LatestRequestGate()
    first = gate.begin("https://www.youtube.com/watch?v=firstVideo1")
    second = gate.begin("https://www.youtube.com/watch?v=secondVide2")
    third = gate.begin("https://www.youtube.com/watch?v=thirdVideo3")
    delivered: list[str] = []

    assert gate.deliver(first, delivered.append, "A") is False
    assert gate.finish(first) is False
    assert gate.deliver(second, delivered.append, "B") is False
    assert gate.finish(second) is False
    assert gate.deliver(third, delivered.append, "C") is True
    assert delivered == ["C"]
    assert gate.finish(third) is True
    assert gate.current is None


def test_app_controller_does_not_apply_stale_metadata_to_the_download_page(tmp_path) -> None:
    controller = AppController.__new__(AppController)
    controller._metadata_gate = LatestRequestGate()
    controller._pending_retry = None
    controller.settings = SimpleNamespace(default_quality="recommended")
    displayed: list[str] = []
    controller.window = SimpleNamespace(
        download_page=SimpleNamespace(show_video=lambda video, **_kwargs: displayed.append(video.video_id))
    )
    first = controller._metadata_gate.begin("A")
    second = controller._metadata_gate.begin("B")
    source = _request(tmp_path).video

    controller._metadata_result(first, replace(source, video_id="A"))
    controller._metadata_result(second, replace(source, video_id="B"))

    assert displayed == ["B"]

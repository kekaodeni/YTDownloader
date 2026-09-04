from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QPixmap

from yt_downloader.ui.motion import MotionManager
from yt_downloader.ui.widgets.thumbnail_crossfade import ThumbnailCrossFadeWidget
from test_download_service import _request


def solid(color: str) -> QPixmap:
    pixmap = QPixmap(60, 34)
    pixmap.fill(QColor(color))
    return pixmap


def test_mid_crossfade_replacement_starts_from_current_composite(qapp, qtbot):
    motion = MotionManager()
    widget = ThumbnailCrossFadeWidget(motion=motion)
    widget.resize(300, 169)
    qtbot.addWidget(widget)
    widget.show()
    widget.setPixmap(solid('red'))
    widget.setPixmap(solid('green'))
    qtbot.wait(60)
    before = widget.grab().toImage().pixelColor(150, 84)
    widget.setPixmap(solid('blue'))
    after = widget.grab().toImage().pixelColor(150, 84)
    assert abs(before.red() - after.red()) <= 3
    assert abs(before.green() - after.green()) <= 3
    assert widget.is_animating
    qtbot.waitUntil(lambda: not widget.is_animating, timeout=1000)
    assert widget.pixmap().toImage().pixelColor(10, 10) == QColor('blue')


def test_reduced_motion_toggle_settles_running_thumbnail(qapp, qtbot):
    motion = MotionManager()
    widget = ThumbnailCrossFadeWidget(motion=motion)
    qtbot.addWidget(widget)
    widget.show()
    widget.setPixmap(solid('red'))
    widget.setPixmap(solid('blue'))
    assert widget.is_animating
    motion.set_reduce_motion(True)
    assert not widget.is_animating
    assert widget.previous_pixmap.isNull()


def test_download_page_uses_crossfade_but_keeps_video_id_isolation(qapp, qtbot, tmp_path):
    from yt_downloader.ui.pages.download_page import DownloadPage

    motion = MotionManager()
    page = DownloadPage(str(tmp_path), motion=motion)
    qtbot.addWidget(page)
    page.show()
    video = _request(tmp_path).video
    page.show_video(video)
    assert page.set_thumbnail('stale-generation', b'not-an-image') is False
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    solid('green').save(buffer, 'PNG')
    assert page.set_thumbnail(video.video_id, bytes(data)) is True
    assert isinstance(page.thumbnail, ThumbnailCrossFadeWidget)
    assert not page.thumbnail.pixmap().isNull()

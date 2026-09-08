from dataclasses import replace
from pathlib import Path
import hashlib
import threading
import pytest
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import QUrl
from yt_downloader.core.models import HistoryRecord, TaskStatus
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.ui.quick_history_images import render_thumbnail, media_key
from conftest import run_frames


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".mp4", ".mkv"])
def test_history_uses_real_video_then_replaced_embedded_cover(quick_window, qtbot, tmp_path, suffix):
    service = FfmpegService(shell_thumbnail_checker=lambda *_: True)
    if not service.available:
        pytest.skip('FFmpeg unavailable')
    media = tmp_path / ('竖屏 视频' + suffix)
    service._run([str(service.ffmpeg_path), '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=180x320:d=2',
                  '-f', 'lavfi', '-i', 'sine=duration=2', '-shortest', '-c:v', 'libx264',
                  '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(media)])
    page = quick_window.history_page
    page.configure_thumbnails(service, tmp_path / 'history-cache')
    record = HistoryRecord('complete', 'video', 'https://example.invalid', '竖屏视频', media,
                           '1080p', media.stat().st_size, None, TaskStatus.COMPLETED, 'now')
    page.set_records([record])
    page.select(record.task_id)
    before = hashlib.sha256(media.read_bytes()).hexdigest()
    page.requestThumbnail(record.task_id)
    qtbot.waitUntil(lambda: bool(page.model.get(0)['thumbnail']), timeout=10000)
    first = page.model.get(0)['thumbnail']
    first_image = QImage(QUrl(first).toLocalFile())
    assert first_image.height() > first_image.width()
    assert first_image.pixelColor(20, 20).blue() > 200
    assert hashlib.sha256(media.read_bytes()).hexdigest() == before
    for color in ('red', 'green'):
        cover = tmp_path / f'{color}.jpg'
        image = QImage(180, 320, QImage.Format_RGB32)
        image.fill(QColor(color)); image.save(str(cover))
        service.embed_cover(media, cover)
        actual_frame = service.extract_frame(media, .5, tmp_path / 'actual-frame.jpg')
        assert QImage(str(actual_frame)).pixelColor(20, 20).blue() > 200
        before = hashlib.sha256(media.read_bytes()).hexdigest()
        page.invalidate_thumbnail(record.task_id)
        qtbot.waitUntil(lambda: bool(page.model.get(0)['thumbnail']) and page.model.get(0)['thumbnail'] != first, timeout=10000)
        current = page.model.get(0)['thumbnail']
        actual = QImage(QUrl(current).toLocalFile()).pixelColor(20, 20)
        expected = QColor(color)
        assert abs(actual.red() - expected.red()) < 10
        assert abs(actual.green() - expected.green()) < 10
        assert actual.blue() < 10
        assert page.state['selectedId'] == record.task_id
        assert hashlib.sha256(media.read_bytes()).hexdigest() == before
        first = current
    # A late result for a deleted row must not resurrect it.
    key = media_key(media)
    page.set_records([])
    page._thumbnail_ready(record.task_id, key, first)
    assert page.model.count == 0


def test_history_ignores_active_missing_and_stale_thumbnail_results(quick_window, tmp_path):
    page = quick_window.history_page
    media = tmp_path / 'video.mp4'; media.write_bytes(b'old')
    record = HistoryRecord('one', 'video', 'url', 'title', media, '1080p', 3, None, TaskStatus.COMPLETED, 'now')
    page.set_records([record])
    old = media_key(media)
    media.write_bytes(b'new contents')
    page._thumbnail_ready('one', old, 'file:///stale.jpg')
    assert not page.model.get(0)['thumbnail']
    page.set_records([replace(record, status=TaskStatus.DOWNLOADING_VIDEO)])
    page._thumbnail_ready('one', media_key(media), 'file:///active.jpg')
    assert not page.model.get(0)['thumbnail']
    media.unlink()
    page._thumbnail_ready('one', old, 'file:///missing.jpg')
    assert not page.model.get(0)['thumbnail']


def test_history_cover_layout_fits_portrait_landscape_and_compact_window(quick_window, qapp, tmp_path):
    from conftest import run_frames, find_item
    from PIL import Image
    records = []
    for name, size in (("portrait", (90, 160)), ("landscape", (160, 90))):
        path = tmp_path / (name + ".png")
        Image.new("RGB", size, "#cf453b").save(path)
        records.append(HistoryRecord(name, name, "url", "完整显示横竖屏封面，多语言长标题 Title", tmp_path / (name + ".mp4"),
                                     "1080p", 100, path, TaskStatus.COMPLETED, "now"))
    quick_window.history_page.set_records(records)
    quick_window._select_page(1)
    for width in (1200, 500):
        quick_window.root.resize(width, 800)
        run_frames(qapp, 400)
        heights = []
        for name, ratio in (("portrait", 90/160), ("landscape", 160/90)):
            cover = find_item(quick_window, "historyCover-" + name)
            assert cover.isVisible()
            assert abs(cover.width()/cover.height() - ratio) < .01
            assert cover.property("imageFillMode") == 1
            assert cover.height() <= cover.parentItem().height() + .1
            assert cover.width() <= cover.parentItem().width() + .1
            heights.append(find_item(quick_window, "history-" + name).height())
        assert abs(heights[0] - heights[1]) < .1

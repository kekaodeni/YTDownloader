"""Capture offline Collection workflow states from the real Qt Quick app."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, DownloadProgress, DownloadRequest, FormatOption, ResolvedMedia, TaskStatus
from yt_downloader.services.media_metadata import resolve_metadata
from yt_downloader.ui.quick_window import MainWindow

CAPTURE = True

def wait(ms=300):
    QTest.qWait(ms)


def collection_fixtures():
    root = Path(__file__).resolve().parents[1]
    bili_fixture = json.loads((root / "tests/fixtures/bilibili_embedded_replay.json").read_text(encoding="utf-8"))
    bili = resolve_metadata(bili_fixture, "https://www.bilibili.com/video/BV1TiGg6kErJ/")
    bili = replace(bili, thumbnail_url=None,
                   entries=tuple(replace(item, thumbnail='') for item in bili.entries))
    youtube = resolve_metadata({
        "_type": "playlist", "id": "PL-offline-preview", "title": "YouTube Playlist UI Preview",
        "extractor_key": "YoutubeTab", "uploader": "Example Channel", "playlist_count": 4,
        "entries": [
            {"id": f"preview-{index}", "title": f"Playlist item {index}",
             "url": f"https://www.youtube.com/watch?v=preview{index:05d}"}
            for index in range(1, 5)
        ],
    }, "https://www.youtube.com/watch?v=preview00001&list=PL-offline-preview")
    return bili, youtube


def save(window, path):
    wait(220)
    image = window.grab()
    if image.isNull() or (CAPTURE and not image.save(str(path))):
        raise RuntimeError(f"Could not capture Qt Quick window: {path}")


def find_visual(window, name):
    found = window.root.findChild(QObject, name)
    if found is not None:
        return found
    pending = [window.root.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def bring_item_into_view(window, name, *, y=260):
    item = find_visual(window, name)
    if item is None or not hasattr(item, "mapToScene"):
        raise RuntimeError(f"Cannot find visual item {name}")
    task_list = window.root.findChild(QObject, "taskList")
    if task_list is not None:
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        content_y = float(task_list.property("contentY"))
        task_list.setProperty("contentY", content_y + point.y() - y)
        wait(180)
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1500)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--smoke-only", action="store_true", help="Run the same states and rendering checks without saving PNGs")
    args = parser.parse_args()
    global CAPTURE
    CAPTURE = not args.smoke_only
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(download_directory=str(args.output), auto_check_updates=False),
                        ytdlp_version="fixture", ffmpeg_description="fixture")
    window.root.resize(args.width, args.height)
    window.show()
    bili, youtube = collection_fixtures()
    warnings = []

    for theme in ("light", "dark"):
        window.theme.set_mode(theme)
        window._select_page(0)
        window.download_page.show_video(bili)
        if window.download_page.state['collectionQualityMode'] != 'RESOLVED_COMMON_FORMATS':
            raise RuntimeError("Bilibili collection did not use its real common formats")
        if '1080p 60 FPS' not in window.download_page.state['collectionQualityLabels']:
            raise RuntimeError("Bilibili common quality options are missing 1080p 60 FPS")
        if find_visual(window, "collectionQualityLabel").property("text") != "画质":
            raise RuntimeError("Resolved collection did not display the ordinary quality label")
        window.scroll_download_to_top()
        wait(250)
        for control in ("modeCombo", "collectionQualityCombo", "directoryField", "collectionItems", "downloadButton"):
            target = find_visual(window, control)
            if target is None or not target.isVisible():
                raise RuntimeError(f"Collection control is missing/hidden: {control}")
        download_button = find_visual(window, "downloadButton")
        button_bottom = download_button.mapToScene(QPointF(download_button.width(), download_button.height())).y()
        if button_bottom > window.root.height() + 1:
            task_list = find_visual(window, "taskList")
            task_list.setProperty("contentY", float(task_list.property("contentY"))
                                  + button_bottom - window.root.height() + 20)
            wait(180)
            button_bottom = download_button.mapToScene(
                QPointF(download_button.width(), download_button.height())).y()
            if button_bottom > window.root.height() + 1:
                raise RuntimeError("Collection primary button remains clipped after scrolling")
        save(window, args.output / f"{theme}-bilibili-collection.png")

        window.download_page.show_video(youtube)
        wait(250)
        window.scroll_download_to_top()
        wait(250)
        if window.download_page.state['collectionQualityMode'] != 'DEFERRED_BATCH_TARGET':
            raise RuntimeError("Flat YouTube playlist did not use deferred batch targets")
        if window.download_page.state['collectionQuality'] != 'highest':
            raise RuntimeError("Deferred batch quality did not default to per-video highest")
        if window.download_page.state['collectionQualityLabels'] != [
                '各视频最高可用', '最高 2160p', '最高 1440p',
                '最高 1080p', '最高 720p']:
            raise RuntimeError("Deferred batch quality options are incorrect")
        if find_visual(window, "collectionQualityLabel").property("text") != "批量画质":
            raise RuntimeError("Deferred collection did not display the batch quality label")
        window.scroll_download_to_top()
        wait(250)
        save(window, args.output / f"{theme}-youtube-playlist.png")

        page = window.download_page
        option = FormatOption("1080p", 1080, 30, "avc1", "mp4a", "MP4", "mp4", "bestvideo+bestaudio",
                              None, True, "bestvideo", is_recommended=True)
        for index, entry in enumerate(youtube.entries):
            video = ResolvedMedia(entry.id, entry.url, entry.title, "Example Channel", 180,
                                  None, None, (option,), extractor_key="Youtube")
            request = DownloadRequest(f"collection-{theme}-{index}", video, option, args.output,
                                      entry.title, playlist_title=youtube.title)
            page.add_task(request)
            if index == 0:
                page.update_task(DownloadProgress(request.task_id, TaskStatus.DOWNLOADING_VIDEO,
                                                  42, 42_000_000, 100_000_000, 1_000_000, 58))
            elif index == 1:
                page.update_task(DownloadProgress(request.task_id, TaskStatus.PENDING))
            elif index == 2:
                page.fail_task(request.task_id, TaskStatus.FAILED)
            else:
                page.update_task(DownloadProgress(request.task_id, TaskStatus.PENDING))
        collection_task_ids = [f"collection-{theme}-{index}" for index in range(len(youtube.entries))]
        if not all(task_id in page.cards for task_id in collection_task_ids):
            raise RuntimeError("Collection children were not registered as standard tasks")
        if find_visual(window, "batch-fixture") is not None:
            raise RuntimeError("Unexpected Collection parent task card")
        task_list = window.root.findChild(QObject, "taskList")
        max_y = max(0.0, float(task_list.property("contentHeight")) - float(task_list.property("height")))
        visible_task = None
        for fraction in (0, .25, .5, .75, 1):
            task_list.setProperty("contentY", max_y * fraction)
            wait(100)
            visible_task = next((find_visual(window, f"task-{task_id}") for task_id in collection_task_ids
                                 if find_visual(window, f"task-{task_id}") is not None
                                 and find_visual(window, f"task-{task_id}").isVisible()), None)
            if visible_task is not None:
                break
        if visible_task is None:
            raise RuntimeError("Collection child task card is missing")
        save(window, args.output / f"{theme}-collection-download-tasks.png")
        warnings.extend(str(item) for item in window.qml_warnings)

    result = {"screenshots": 6 if CAPTURE else 0, "qml_warnings": warnings,
              "dpr": window.root.devicePixelRatio(), "size": [args.width, args.height],
              "metadata_source": "offline extractor fixtures in the running QML application"}
    (args.output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    window.update(allowClose=True)
    window.close()
    app.quit()


if __name__ == "__main__":
    main()

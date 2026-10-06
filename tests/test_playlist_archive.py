from types import SimpleNamespace
from dataclasses import replace
from test_download_archive import _success
from yt_downloader.services.archive_service import ArchiveRepository
from yt_downloader.services.media_metadata import resolve_metadata
from yt_downloader.ui.quick_download import DownloadPresenter


def _page(tmp_path):
    archive = ArchiveRepository(tmp_path / 'history.db')
    request, result = _success(tmp_path)
    archive.record_download(request, result)
    media = resolve_metadata(dict(_type='playlist', id='list', extractor_key='Youtube', title='List', entries=[
        dict(id=request.video.video_id, ie_key='Youtube', title='Downloaded', url=request.video.url),
        dict(id='new', ie_key='Youtube', title='New', url='https://youtu.be/new'),
        dict(id='locked', ie_key='Youtube', title='Members', availability='subscriber_only', url='https://youtu.be/locked'),
        None]), 'https://www.youtube.com/playlist?list=list')
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.configure_archive(archive)
    page.show_video(media)
    return page


def test_playlist_downloaded_badges(qapp, tmp_path):
    page = _page(tmp_path)
    assert [page.entries.get(i)['statusKey'] for i in range(4)] == [
        'playlist.downloaded', 'playlist.available', 'playlist.login_required', 'playlist.unavailable']
    assert not page.entries.get(0)['unavailable']
    assert '2026-10-06' in page.entries.get(0)['archiveDetail']


def test_playlist_duplicate_default_selection(qapp, tmp_path):
    page = _page(tmp_path)
    assert page.state['selectedCount'] == 1
    assert page.state['skippedDownloadedCount'] == 1
    assert not page.entries.get(0)['selected'] and page.entries.get(1)['selected']
    page.selectEntry(0, True)
    assert page.entries.get(0)['selected'] and page.state['skippedDownloadedCount'] == 0
    assert page.state['selectedCount'] == 2


def test_playlist_filter_all(qapp, tmp_path):
    page = _page(tmp_path)
    page.selectCollectionFilter('all')
    assert page.filteredEntries.rowCount() == 4


def test_playlist_filter_downloaded(qapp, tmp_path):
    page = _page(tmp_path)
    page.selectCollectionFilter('downloaded')
    assert page.filteredEntries.rowCount() == 1
    assert page.filteredEntries.get(0)['index'] == 0
    page.selectAllEntries(True)
    assert page.state['selectedCount'] == 2  # hidden new item retains selection
    assert page.state['collectionSelectState'] == 2


def test_playlist_filter_not_downloaded(qapp, tmp_path):
    page = _page(tmp_path)
    page.selectCollectionFilter('not_downloaded')
    assert [page.filteredEntries.get(i)['index'] for i in range(3)] == [1, 2, 3]


def test_playlist_tristate_selection(qapp, tmp_path):
    page = _page(tmp_path)
    assert page.state['collectionSelectState'] == 1
    page.selectAllEntries(True)
    assert page.state['collectionSelectState'] == 2
    page.selectAllEntries(False)
    assert page.state['collectionSelectState'] == 0
    page.selectEntry(0, True)
    assert page.state['collectionSelectState'] == 1


def test_youtube_playlist_quality_policy_preserved(qapp, tmp_path):
    page = _page(tmp_path)
    assert page.state['collectionQualityLabels'] == ['各视频最高可用', '最高 2160p', '最高 1440p', '最高 1080p', '最高 720p']
    page.selectCollectionFilter('downloaded')
    page.selectCollectionQuality(3)
    assert page.state['collectionQuality'] == 'cap:1080p'


def test_bilibili_collection_semantic_quality_preserved(qapp, tmp_path):
    import json
    from pathlib import Path
    from yt_downloader.services.media_metadata import resolve_metadata
    from yt_downloader.ui.quick_download import DownloadPresenter
    raw = json.loads(Path('tests/fixtures/bilibili_embedded_replay.json').read_text(encoding='utf-8'))
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.show_video(resolve_metadata(raw, 'https://www.bilibili.com/video/BV1TiGg6kErJ/'))
    before = page.state['collectionQualityLabels']
    page.selectCollectionFilter('not_downloaded')
    assert page.state['collectionQualityLabels'] == before and '1080p 60 FPS' in before


def test_playlist_archive_uses_one_lookup_and_keeps_1000_deferred(qapp, tmp_path):
    from yt_downloader.services.archive_service import ArchiveRepository
    from time import perf_counter
    archive = ArchiveRepository(tmp_path / 'large.db')
    calls = []
    original = archive.lookup_many
    archive.lookup_many = lambda ids: (calls.append(len(ids)), original(ids))[1]
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.configure_archive(archive)
    media = resolve_metadata(dict(_type='playlist', extractor_key='Youtube', entries=[
        dict(id=str(i), title=str(i), url=f'https://youtu.be/{i}', ie_key='Youtube') for i in range(1000)]),
        'https://www.youtube.com/playlist?list=large')
    start = perf_counter()
    page.show_video(media)
    assert calls == [1000]
    assert page.state['selectedCount'] == 1000
    assert all(not entry.formats and not entry.embedded for entry in media.entries)
    assert perf_counter() - start < 3

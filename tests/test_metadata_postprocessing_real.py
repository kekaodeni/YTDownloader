"""Real native yt-dlp download/merge/postprocess and bundled ffprobe outputs."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import pickle
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest

from yt_downloader.core.models import DownloadRequest
from yt_downloader.services.cookie_service import ReadOnlyCookieYoutubeDL
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.ffmpeg_service import FfmpegService
from yt_downloader.services.media_metadata import resolve_metadata


def test_chapters_survive_normalization_and_metadata_ipc():
    source = {'id': 'chapters', 'title': 'Chapter source', 'chapters': [
        {'start_time': 0, 'end_time': 2, 'title': 'One'},
        {'start_time': 2, 'end_time': 4, 'title': 'Two'},
        {'start_time': 4, 'end_time': 6, 'title': 'Three'},
    ]}
    media = resolve_metadata(source, 'https://example.test/video')
    task_media = pickle.loads(pickle.dumps(media))
    assert [(chapter.start_time, chapter.end_time, chapter.title)
            for chapter in task_media.chapters] == [(0, 2, 'One'), (2, 4, 'Two'), (4, 6, 'Three')]
    assert task_media.raw == {}


def test_collection_entries_keep_their_own_chapters():
    info = {'_type': 'playlist', 'chapters': [{'start_time': 0, 'title': 'Parent'}], 'entries': [
        {'id': 'one', 'url': 'https://example.test/one',
         'chapters': [{'start_time': 0, 'end_time': 2, 'title': 'First entry'}]},
        {'id': 'two', 'url': 'https://example.test/two',
         'chapters': [{'start_time': 0, 'end_time': 3, 'title': 'Second entry'}]},
    ]}
    media = resolve_metadata(info, 'https://example.test/list')
    assert [entry.chapters[0].title for entry in media.entries] == ['First entry', 'Second entry']


def test_embedded_collection_task_keeps_entry_chapters_and_postprocessing_options(qapp, tmp_path, source_media):
    from yt_downloader.app import AppController
    from yt_downloader.core.models import AppSettings
    from yt_downloader.ui.quick_download import DownloadPresenter

    info = {'_type': 'multi_video', 'id': 'list', 'title': 'List', 'extractor_key': 'BiliBili',
            'chapters': [{'start_time': 0, 'end_time': 6, 'title': 'Parent chapter'}],
            'entries': [source_media]}
    media = resolve_metadata(info, 'https://example.test/list')
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _value: ''))
    page.show_video(media)
    page.setAdvancedToggle('embedMetadata', True)
    page.setAdvancedToggle('embedChapters', True)
    page.setAdvancedToggle('embedThumbnail', True)
    requests = []
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(selected_profile=None))
    controller.settings = AppSettings()
    controller.history = SimpleNamespace(upsert=lambda _record: None)
    controller.queue = SimpleNamespace(enqueue=requests.append)
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: pytest.fail(str(error))
    controller.enqueue_collection(media, media.entries)
    assert len(requests) == 1
    request = requests[0]
    assert request.embed_metadata and request.embed_chapters
    assert request.embed_thumbnail
    assert request.metadata_language == controller.settings.language
    assert request.video.chapters == media.entries[0].chapters
    assert len(request.video.chapters) == 3
    assert request.video.chapters != media.chapters


def test_audio_conversion_processor_is_kept_before_metadata(tmp_path, source_media):
    from dataclasses import replace
    from yt_downloader.services.download_options import media_options, prepare_request

    media = resolve_metadata(source_media, source_media['webpage_url'])
    request = DownloadRequest('audio-pp', media, media.formats[0], tmp_path, 'audio',
                              media_mode='audio_only', audio_codec='mp3', embed_metadata=True)
    processors = media_options(prepare_request(request))['postprocessors']
    assert [item['key'] for item in processors] == ['FFmpegExtractAudio', 'FFmpegMetadata']
    assert processors[-1]['add_chapters'] is False
    assert 'postprocessors' not in media_options(prepare_request(
        replace(request, audio_codec='original', embed_metadata=False)))


def test_advanced_qml_toggles_reach_immutable_task_snapshot(quick_window, qapp, tmp_path, source_media):
    from conftest import click_item, find_item, run_frames
    from test_download_view_scroll import scroll_to
    from yt_downloader.app import AppController
    from yt_downloader.services.download_options import prepare_request

    media = resolve_metadata(source_media, source_media['webpage_url'])
    page = quick_window.download_page
    quick_window.root.resize(1100, 900)
    page.show_video(media)
    run_frames(qapp, 160)
    click_item(quick_window, find_item(quick_window, 'advancedOptionsToggle'))
    run_frames(qapp, 220)
    def click_toggle(name):
        row = find_item(quick_window, name)
        scroll_to(quick_window, row)
        run_frames(qapp, 50)
        switch = next(item for item in row.childItems()
                      if item.metaObject().indexOfProperty('checkable') >= 0)
        click_item(quick_window, switch)

    for name in ('embedThumbnail', 'embedMetadata', 'embedChapters'):
        click_toggle(name)
        assert page.state[name] is True

    requests = []
    controller = AppController.__new__(AppController)
    controller.window = quick_window
    controller.history = SimpleNamespace(upsert=lambda _record: None)
    controller.queue = SimpleNamespace(enqueue=requests.append)
    controller._persisted_task_stages = {}
    controller.settings = quick_window.settings_page.current_settings()
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: pytest.fail(str(error))
    page.download_requested.connect(controller.enqueue_download)
    page.requestDownload()
    assert len(requests) == 1
    request = prepare_request(requests[0])
    assert request.embed_thumbnail and request.embed_metadata and request.embed_chapters
    assert request.metadata_language == controller.settings.language == 'zh-CN'
    assert len(request.video.chapters) == 3
    # Subsequent UI edits cannot alter a queued task's option snapshot.
    for name in ('embedThumbnail', 'embedMetadata', 'embedChapters'):
        click_toggle(name)
        assert page.state[name] is False
    assert request.embed_thumbnail and request.embed_metadata and request.embed_chapters


@pytest.fixture
def source_media(tmp_path):
    tools = FfmpegService()
    assert tools.ffmpeg_path and tools.ffprobe_path
    video, audio = tmp_path/'source.mp4', tmp_path/'source.m4a'
    from PIL import Image, ImageDraw
    for name, size, color in (('low.png', (120, 68), 'blue'), ('cover.webp', (320, 180), 'orange'),
                              ('second.webp', (320, 180), 'purple')):
        image = Image.new('RGB', size, color)
        ImageDraw.Draw(image).rectangle((10, 10, 80, 50), fill='green')
        image.save(tmp_path / name)
    for output, args in (
        (video, ['-f','lavfi','-i','testsrc2=s=320x180:d=6:r=10','-c:v','libx264','-pix_fmt','yuv420p']),
        (audio, ['-f','lavfi','-i','sine=frequency=440:duration=6','-c:a','aac']),
    ):
        subprocess.run([str(tools.ffmpeg_path),'-hide_banner','-loglevel','error','-y',*args,str(output)],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(tmp_path)))
    worker = threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    info = {
        'id': 'chapter-fixture', 'title': '真实媒体信息测试', 'uploader': 'Fixture uploader',
        'description': 'Fixture description with media metadata', 'upload_date': '20260930',
        'webpage_url': 'https://example.test/chapter-fixture', 'duration': 6,
        'extractor': 'fixture', 'extractor_key': 'Generic',
        'thumbnail': base + '/cover.webp',
        'thumbnails': [
            {'id': 'low', 'url': base + '/low.png', 'width': 120, 'height': 68},
            {'id': 'best', 'url': base + '/cover.webp', 'width': 320, 'height': 180},
        ],
        'chapters': [{'start_time': n*2, 'end_time': (n+1)*2, 'title': title}
                     for n,title in enumerate(('开场', '第二章', '总结'))],
        'formats': [
            {'format_id':'v','url':base+'/source.mp4','ext':'mp4','vcodec':'h264','acodec':'none','width':320,'height':180,'fps':10},
            {'format_id':'a','url':base+'/source.m4a','ext':'m4a','vcodec':'none','acodec':'aac','abr':64},
        ],
    }
    try:
        yield info
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.integration
@pytest.mark.parametrize(('metadata','chapters'), [(False,False),(False,True),(True,False),(True,True)])
def test_final_mkv_contains_requested_native_chapters_and_metadata(tmp_path, source_media, metadata, chapters):
    infofile = tmp_path/'source.info.json'
    infofile.write_text(json.dumps(source_media,ensure_ascii=False),encoding='utf-8')
    media = resolve_metadata(source_media, source_media['webpage_url'])
    request = DownloadRequest('real-pp', media, media.formats[0], tmp_path/'out', '成品',
                              embed_metadata=metadata, embed_chapters=chapters, remux_container='mkv')
    assert request.format.final_ext == 'mp4'  # The native remux must change the actual container.
    chain = []
    def factory(options):
        def hook(data):
            if data['status'] == 'started':
                chain.append(data['postprocessor'])
        ydl = ReadOnlyCookieYoutubeDL({**options,
                                      'postprocessor_hooks': [*options['postprocessor_hooks'],hook]})
        # Only extraction is offline: use yt-dlp's public info-file API. All
        # media IO, native merger, postprocessors and file commit are real.
        ydl.download = lambda _urls: ydl.download_with_info_file(str(infofile))
        return ydl
    result = DownloadService(ydl_factory=factory).download(request, lambda _p: None, threading.Event())
    probe = subprocess.run([str(FfmpegService().ffprobe_path),'-v','error','-show_chapters','-show_format',
                            '-of','json',str(result.file_path)],check=True,capture_output=True,
                           text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
    payload = json.loads(probe.stdout)
    # Final output, not the options passed to the downloader, is the contract.
    assert len(payload.get('chapters',[])) == (3 if chapters else 0)
    tags = {key.casefold(): value for key,value in payload['format'].get('tags',{}).items()}
    if metadata:
        assert tags['title'] == source_media['title']
        assert tags['artist'] == source_media['uploader']
        assert tags['description'] == source_media['description']
        assert tags['date'] == source_media['upload_date']
        assert tags['purl'] == source_media['webpage_url']
    else:
        assert 'artist' not in tags and 'description' not in tags
    assert 'matroska' in payload['format']['format_name']
    assert chain.index('Merger') < chain.index('VideoRemuxer')
    if metadata or chapters:
        assert chain.index('VideoRemuxer') < chain.index('Metadata')
    else:
        assert 'Metadata' not in chain


def _download_native_fixture(tmp_path, source_media, *, playlist_item_index=None, **flags):
    infofile = tmp_path / 'source.info.json'
    infofile.write_text(json.dumps(source_media, ensure_ascii=False), encoding='utf-8')
    entry = source_media['entries'][playlist_item_index - 1] if playlist_item_index else source_media
    media = resolve_metadata(entry, source_media['webpage_url'])
    request = DownloadRequest('cover-pp', media, media.formats[0], tmp_path / 'out', '成品',
                              remux_container='mkv', playlist_item_index=playlist_item_index, **flags)
    chain, thumbnails = [], []

    def factory(options):
        def hook(data):
            if data['status'] != 'started':
                return
            name = data['postprocessor']
            chain.append(name)
            if name == 'EmbedThumbnail':
                selected = next(item for item in reversed(data['info_dict']['thumbnails'])
                                if item.get('filepath'))
                path = Path(selected['filepath'])
                assert path.is_file()
                thumbnails.append((path, path.read_bytes(), selected['url']))

        # Native info-file loading otherwise removes playlist entries as private
        # fields. Preserve this local fixture's entries for real native selection.
        ydl = ReadOnlyCookieYoutubeDL({**options, 'clean_infojson': False,
                                      'postprocessor_hooks': [*options['postprocessor_hooks'], hook]})
        started = False

        def download(_urls):
            nonlocal started
            assert not started, 'Fixture must not fall back to external re-extraction'
            started = True
            return ydl.download_with_info_file(str(infofile))

        ydl.download = download
        return ydl

    result = DownloadService(ydl_factory=factory).download(request, lambda _p: None, threading.Event())
    probe = subprocess.run([
        str(FfmpegService().ffprobe_path), '-v', 'error', '-show_chapters', '-show_format',
        '-show_streams', '-of', 'json', str(result.file_path),
    ], check=True, capture_output=True, text=True, encoding='utf-8',
        creationflags=subprocess.CREATE_NO_WINDOW)
    return result, json.loads(probe.stdout), chain, thumbnails


def _assert_real_cover(tmp_path, result, probe, thumbnails, expected_url):
    from PIL import Image

    covers = [stream for stream in probe['streams']
              if str(stream.get('tags', {}).get('filename', '')).startswith('cover.')
              and str(stream.get('tags', {}).get('mimetype', '')).startswith('image/')]
    assert len(covers) == 1
    cover = covers[0]
    destination = tmp_path / cover['tags']['filename']
    subprocess.run([
        str(FfmpegService().ffmpeg_path), '-v', 'error', '-y',
        f'-dump_attachment:{cover["index"]}', str(destination), '-i', str(result.file_path),
        '-map', '0:V:0', '-frames:v', '1', '-f', 'null', 'NUL',
    ], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert destination.is_file()
    with Image.open(destination) as image:
        image.verify()
    assert thumbnails and all(item[2] == expected_url for item in thumbnails)
    assert hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(thumbnails[0][1]).digest()
    # Native EmbedThumbnail owns its downloaded thumbnail and removes it after use.
    assert all(not path.exists() for path, _content, _url in thumbnails)
    assert not list(result.file_path.parent.glob('*.webp'))


@pytest.mark.integration
def test_embed_thumbnail_real_output(tmp_path, source_media):
    result, probe, chain, thumbnails = _download_native_fixture(
        tmp_path, source_media, embed_thumbnail=True)
    _assert_real_cover(tmp_path, result, probe, thumbnails, source_media['thumbnail'])
    assert probe['chapters'] == []
    assert chain.index('VideoRemuxer') < chain.index('EmbedThumbnail') < chain.index('MoveFiles')


@pytest.mark.integration
def test_embed_chapters_real_output(tmp_path, source_media):
    _result, probe, _chain, thumbnails = _download_native_fixture(
        tmp_path, source_media, embed_chapters=True)
    assert len(probe['chapters']) == 3
    assert [chapter['tags']['title'] for chapter in probe['chapters']] == ['开场', '第二章', '总结']
    assert not thumbnails
    assert not any(stream.get('tags', {}).get('filename', '').startswith('cover.') for stream in probe['streams'])


@pytest.mark.integration
def test_embed_thumbnail_and_chapters_together(tmp_path, source_media):
    result, probe, chain, thumbnails = _download_native_fixture(
        tmp_path, source_media, embed_thumbnail=True, embed_metadata=True, embed_chapters=True)
    _assert_real_cover(tmp_path, result, probe, thumbnails, source_media['thumbnail'])
    assert len(probe['chapters']) == 3
    tags = {key.casefold(): value for key, value in probe['format']['tags'].items()}
    assert tags['title'] == source_media['title']
    assert tags['artist'] == source_media['uploader']
    assert tags['description'] == source_media['description']
    assert chain.index('Merger') < chain.index('VideoRemuxer') < chain.index('Metadata')
    assert chain.index('Metadata') < chain.index('EmbedThumbnail') < chain.index('MoveFiles')


@pytest.mark.integration
@pytest.mark.parametrize('extractor', ['Youtube', 'BiliBili'])
def test_collection_children_embed_their_own_cover_not_parent_or_sibling(tmp_path, source_media, extractor):
    from copy import deepcopy

    base = source_media['thumbnail'].rsplit('/', 1)[0]
    children = [deepcopy(source_media), deepcopy(source_media)]
    for index, child in enumerate(children, 1):
        child.update(id=f'child-{index}', title=f'Child {index}', extractor_key=extractor)
    children[1]['thumbnail'] = base + '/second.webp'
    children[1]['thumbnails'] = [{'id': 'second', 'url': children[1]['thumbnail'], 'width': 320, 'height': 180}]
    collection = {'_type': 'playlist' if extractor == 'Youtube' else 'multi_video',
                  'id': 'collection', 'title': 'Parent', 'extractor_key': extractor,
                  'extractor': extractor.lower(),
                  'webpage_url': 'https://example.test/collection',
                  'thumbnail': base + '/low.png',
                  'thumbnails': [{'id': 'parent', 'url': base + '/low.png'}],
                  'chapters': [{'start_time': 0, 'end_time': 6, 'title': 'Parent chapter'}],
                  'entries': children}
    hashes = []
    for index, child in enumerate(children, 1):
        result, probe, _chain, thumbnails = _download_native_fixture(
            tmp_path, collection, playlist_item_index=index,
            embed_thumbnail=True, embed_metadata=True, embed_chapters=True)
        _assert_real_cover(tmp_path, result, probe, thumbnails, child['thumbnail'])
        assert [chapter['tags']['title'] for chapter in probe['chapters']] == ['开场', '第二章', '总结']
        assert probe['format']['tags']['title'] == child['title']
        hashes.append(hashlib.sha256(thumbnails[0][1]).hexdigest())
    assert hashes[0] != hashes[1]

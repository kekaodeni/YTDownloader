"""Season enrichment contracts, based on the audited ss46089 API shapes."""
from copy import deepcopy
import io
import json
import threading
from types import SimpleNamespace

import pytest

from yt_downloader.core.errors import OperationCancelled
from yt_downloader.core.formats import normalize_formats
from yt_downloader.core.quality_target import choose_quality
from yt_downloader.services.media_metadata import resolve_metadata
from yt_downloader.services.media_resolver import MediaResolver

URL = 'https://www.bilibili.com/bangumi/play/ss46089'


def formats(tiers=(16, 32, 64, 80, 112, 116, 120, 122, 125, 126), prefix='ref'):
    heights = {16: 360, 32: 480, 64: 720, 80: 1080, 112: 1080,
               116: 1080, 120: 2160, 122: 2160, 125: 886, 126: 1890}
    return [dict(format_id=f'{prefix}-{tier}-{codec}', quality=tier, height=heights[tier],
                 width=3840 if tier >= 120 else 1920, fps=fps, ext='mp4',
                 url='https://cdn.example.invalid/media', vcodec=codec, acodec='mp4a',
                 dynamic_range='HDR10' if tier == 125 else 'DV' if tier == 126 else 'SDR',
                 format='SDR增强' if tier == 122 else '')
            for tier in tiers for codec, fps in [('avc1', 58.7), ('hev1', 59.94), ('av01', 60.0)]]


def flat():
    return dict(_type='playlist', id='46089', title='Season', extractor_key='BiliBiliBangumiSeason',
                entries=[dict(_type='url', id=str(779775 + i), ie_key='BiliBiliBangumi',
                              url=f'https://www.bilibili.com/bangumi/play/ep{779775 + i}')
                         for i in range(28)])


def season():
    return dict(code=0, result=dict(season_id=46089, title='Season', cover='https://images.example/season.png',
                episodes=[dict(id=779775 + i, title=str(i + 1), long_title=f'Episode {i + 1}',
                               duration=1559933, cover=f'https://images.example/episode-{i + 1}.png',
                               status=13, badge='会员', rights={'allow_download': 0}) for i in range(28)]))


def resolver(info=None, payload=None, failed=(), cancel=None):
    seen = SimpleNamespace(extractions=[], requests=[], options=None)
    class YDL:
        def __init__(self, options): seen.options = options
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def sanitize_info(self, value): return value
        def urlopen(self, request):
            seen.requests.append(request.url)
            if cancel: cancel.set()
            return io.BytesIO(json.dumps(payload or season()).encode())
        def extract_info(self, url, download=False):
            assert not download
            seen.extractions.append(url)
            if url == URL: return deepcopy(info or flat())
            if url in failed:
                from yt_dlp.utils import DownloadError
                raise DownloadError('Not available')
            return dict(id=url.rsplit('ep', 1)[-1], title='Reference', extractor_key='BiliBiliBangumi',
                        thumbnail='https://images.example/native-season.png', formats=formats())
    return MediaResolver(ydl_factory=YDL, require_deno=False), seen


def test_bilibili_bangumi_collection_metadata():
    service, _ = resolver()
    media = service.fetch_metadata(URL, include_thumbnail=False)
    assert len(media.entries) == 28
    assert media.entries[0].title == '1 Episode 1'
    assert media.entries[0].duration == pytest.approx(1559.933)
    assert all(entry.available and not entry.embedded and not entry.formats for entry in media.entries)
    assert media.collection_quality_mode == 'REFERENCE_EPISODE_FORMATS'


def test_bilibili_bangumi_parent_thumbnail():
    service, _ = resolver()
    assert service.fetch_metadata(URL, include_thumbnail=False).thumbnail_url == season()['result']['cover']
    info = flat()
    info['_collection_reference'] = {'thumbnail': 'https://images.example/reference.png'}
    info['entries'][0]['thumbnail'] = 'https://images.example/first.png'
    assert resolve_metadata(info, URL).thumbnail_url.endswith('reference.png')
    info['thumbnails'] = [{'url': 'https://images.example/best.png', 'width': 1000},
                          {'url': 'https://images.example/small.png', 'width': 10}]
    assert resolve_metadata(info, URL).thumbnail_url.endswith('best.png')
    info['thumbnail'] = 'https://images.example/own.png'
    assert resolve_metadata(info, URL).thumbnail_url.endswith('own.png')
    del info['thumbnail'], info['thumbnails'], info['_collection_reference']
    assert resolve_metadata(info, URL).thumbnail_url.endswith('first.png')


def test_bilibili_bangumi_entry_thumbnails():
    info = flat()
    info['entries'][0]['thumbnail'] = 'https://images.example/upstream.png'
    info['entries'][1]['thumbnails'] = [{'url': 'https://images.example/upstream-best.png'}]
    service, _ = resolver(info)
    media = service.fetch_metadata(URL, include_thumbnail=False)
    assert media.entries[0].thumbnail.endswith('upstream.png')
    assert media.entries[1].thumbnail.endswith('upstream-best.png')
    assert len({entry.thumbnail for entry in media.entries}) == 28
    assert all(entry.thumbnail != media.thumbnail_url for entry in media.entries)


def test_bilibili_bangumi_quality_probe():
    service, seen = resolver()
    media = service.fetch_metadata(URL, include_thumbnail=False)
    assert seen.extractions == [URL, flat()['entries'][0]['url']]
    assert len(seen.requests) == 1
    assert seen.options['extract_flat'] == 'in_playlist'
    assert media.collection_quality_formats
    # A failed first episode must not prevent reference discovery or erase entries.
    service, seen = resolver(failed=(flat()['entries'][0]['url'],))
    assert service.fetch_metadata(URL, include_thumbnail=False).collection_quality_formats
    assert seen.extractions[-1] == flat()['entries'][1]['url']


def test_bilibili_bangumi_semantic_quality_list(qapp, tmp_path):
    from yt_downloader.ui.quick_download import DownloadPresenter
    service, _ = resolver()
    media = service.fetch_metadata(URL, include_thumbnail=False)
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.show_video(media)
    labels = page.state['collectionQualityLabels']
    assert {'2160p 4K SDR增强 60 FPS', '2160p 4K 60 FPS', '1080p 高码率',
            '1080p', '1080p 60 FPS', 'HDR 60 FPS', '杜比视界 60 FPS'} <= set(labels)
    assert len(labels) == len(set(labels))
    assert not any('QN' in label or '886p' in label or '1890p' in label for label in labels)
    index = labels.index('1080p 高码率')
    page.selectCollectionQuality(index)
    received = []
    page.collection_download_requested.connect(lambda *args: received.append(args))
    page.selectAllEntries(True)
    page.requestDownload()
    assert all(entry.quality_target == 'bilibili:112' and entry.selected_format is None
               for entry in received[0][1])


def test_bilibili_bangumi_quality_fallback():
    options = normalize_formats(formats((80, 116, 120), 'episode17'), extractor_key='BiliBiliBangumi')
    assert choose_quality(options, 'bilibili:112').site_quality == 80
    assert choose_quality(options, 'bilibili:122').site_quality == 120
    assert choose_quality(options, 'bilibili:116').site_quality == 116
    assert choose_quality(options, 'bilibili:116').video_format_id.startswith('episode17-')


def test_enrichment_cancellation():
    cancel = threading.Event()
    service, seen = resolver(cancel=cancel)
    with pytest.raises(OperationCancelled):
        service.fetch_metadata(URL, cancel, include_thumbnail=False)
    assert seen.extractions == [URL]


def test_failed_enrichment_keeps_flat_entries():
    service, _ = resolver(payload={'code': -404})
    media = service.fetch_metadata(URL, include_thumbnail=False)
    assert len(media.entries) == 28
    assert media.collection_quality_formats  # reference can still supply quality


def test_failed_references_are_bounded_and_keep_deferred_list():
    service, seen = resolver(failed=tuple(entry['url'] for entry in flat()['entries']))
    media = service.fetch_metadata(URL, include_thumbnail=False)
    assert len(seen.extractions) == 4  # parent plus at most three references
    assert len(media.entries) == 28 and len({e.thumbnail for e in media.entries}) == 28
    assert media.collection_quality_mode == 'DEFERRED_BATCH_TARGET'


def test_current_episode_is_reference_and_target_does_not_depend_on_other_children():
    from yt_downloader.services.bilibili_bangumi import enrich_season
    service, seen = resolver()
    with service.ydl_factory({}) as ydl:
        info = enrich_season(ydl, flat(), URL + '?ep_id=779778')
    assert seen.extractions == [flat()['entries'][3]['url']]
    media = resolve_metadata(info, URL)
    assert media.collection_quality_formats
    # Deferred children deliberately have no formats to intersect or filter out.
    assert all(not e.formats for e in media.entries)


def test_cookie_and_network_options_reach_reference_unchanged():
    from yt_downloader.core.models import CookieProfile
    from yt_downloader.services.network_policy import NetworkPolicy
    service, seen = resolver()
    service.cookie_profile = CookieProfile('profile', 'Bilibili', 'browser', browser='firefox')
    service.network_policy = NetworkPolicy('custom', 'http://127.0.0.1:8000')
    service.fetch_metadata(URL, include_thumbnail=False)
    assert seen.options['cookiesfrombrowser'][0] == 'firefox'
    assert seen.options['proxy'] == 'http://127.0.0.1:8000'
    assert len(seen.extractions) == 2


def test_bangumi_task_snapshot_keeps_own_cover_and_semantic_target(qapp, tmp_path):
    from dataclasses import replace
    from yt_downloader.app import AppController
    from yt_downloader.core.models import AppSettings
    from yt_downloader.services.history_service import HistoryRepository
    from yt_downloader.ui.quick_download import DownloadPresenter
    service, _ = resolver()
    media = service.fetch_metadata(URL, include_thumbnail=False)
    page = DownloadPresenter(str(tmp_path), SimpleNamespace(add=lambda _: ''))
    page.show_video(media)
    requests = []
    controller = AppController.__new__(AppController)
    controller.window = SimpleNamespace(download_page=page, cookies=SimpleNamespace(selected_profile=None))
    controller.settings = AppSettings()
    controller.history = HistoryRepository(tmp_path / 'history.db')
    controller.queue = SimpleNamespace(enqueue=requests.append)
    controller.refresh_history = lambda: None
    controller.show_error = lambda error: (_ for _ in ()).throw(AssertionError(error))
    controller.enqueue_collection(media, (replace(media.entries[16], quality_target='bilibili:112'),))
    assert len(requests) == 1
    request = requests[0]
    assert request.resolve_before_download and request.preferred_quality == 'bilibili:112'
    assert request.video.url == media.entries[16].url
    assert request.video.thumbnail_url == media.entries[16].thumbnail
    assert request.video.formats == ()


def test_bangumi_qml_uses_batch_label_and_preserves_selection(qapp, quick_window):
    from dataclasses import replace
    from conftest import find_item, run_frames, click_item
    service, _ = resolver()
    media = service.fetch_metadata(URL, include_thumbnail=False)
    # Offline GUI regression only; the live GUI separately uses fetched real covers.
    media = replace(media, thumbnail_url=None,
                    entries=tuple(replace(e, thumbnail='') for e in media.entries))
    quick_window.download_page.show_video(media)
    run_frames(qapp, 130)
    combo = find_item(quick_window, 'collectionQualityCombo')
    assert combo.property('accessibleName') == '批量画质'
    assert combo.property('count') == len(media.collection_quality_formats)
    click_item(quick_window, find_item(quick_window, 'collectionSelectAll'))
    run_frames(qapp, 100)
    assert quick_window.download_page.state['selectedCount'] == 28


def test_deferred_episode_download_uses_own_formats_and_preserves_own_cover(tmp_path, monkeypatch):
    from dataclasses import replace
    from test_download_service import _request, FakeYDL
    from yt_downloader.core.models import CookieProfile
    from yt_downloader.services.download_service import DownloadService
    template = _request(tmp_path)
    profile = CookieProfile('profile', 'Bilibili', 'browser', browser='firefox')
    child = resolve_metadata(dict(id='779791', extractor_key='BiliBiliBangumi', title='Episode 17',
                                 thumbnail='https://images.example/native-season.png',
                                 formats=formats((80, 116, 120), 'episode17')),
                             'https://www.bilibili.com/bangumi/play/ep779791')
    class Resolver:
        def __init__(self, **options): assert options['cookie_profile'] == profile
        def fetch_metadata(self, url, *args, **kwargs):
            assert url == child.url
            return child
    monkeypatch.setattr('yt_downloader.services.media_resolver.MediaResolver', Resolver)
    request = replace(template, resolve_before_download=True, preferred_quality='bilibili:112',
                      cookie_profile=profile,
                      video=replace(template.video, url=child.url,
                                    thumbnail_url='https://images.example/episode17.png'))
    progress = []
    result = DownloadService(ydl_factory=FakeYDL, require_tools=False,
                             media_validator=lambda _: True).download(request, progress.append, threading.Event())
    assert 'episode17-80-' in FakeYDL.last_options['format']
    assert 'ref-' not in FakeYDL.last_options['format']
    assert FakeYDL.last_options['cookiesfrombrowser'] == ('firefox',)
    assert any(item.resolved_thumbnail_url == request.video.thumbnail_url for item in progress)
    assert result.resolved_media.thumbnail_url == request.video.thumbnail_url

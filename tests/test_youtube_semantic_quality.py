"""YouTube quality tiers are distinct from encoded pixel dimensions."""
import json
from pathlib import Path

import pytest

from yt_downloader.core.formats import normalize_formats, apply_codec_preference
from yt_downloader.core.models import CodecPreference
from yt_downloader.core.quality_target import choose_quality


def video(tier, width, height, *, note=None, fps=30, **fields):
    return dict(format_id=f'v{tier}', width=width, height=height, fps=fps,
                format_note=f'{tier}p' if note is None else note,
                vcodec='avc1', acodec='mp4a', ext='mp4', **fields)


def options(*formats, extractor='Youtube'):
    return normalize_formats(formats, extractor_key=extractor)


@pytest.mark.parametrize('tier,width,height', [(2160,3840,2160),(1440,2560,1440),
                                              (1080,1920,1080),(720,1280,720)])
def test_youtube_standard_16_9_quality(tier, width, height):
    result=options(video(tier,width,height))[0]
    assert result.semantic_height == result.display_height == tier
    assert (result.width,result.height)==(width,height)


@pytest.mark.parametrize('tier,width,height,label',[
    (2160,3840,1920,'2160p 4K 60 FPS'), (1440,2560,1280,'1440p 2K 60 FPS'),
    (1080,1920,960,'1080p 60 FPS'), (720,1280,640,'720p 60 FPS'),
    (480,854,428,'480p'), (360,640,320,'360p'), (240,426,214,'240p'),
    (144,256,128,'144p')])
def test_youtube_ultrawide_uses_semantic_tier(tier,width,height,label):
    fps=60 if tier>=720 else 30
    result=options(video(tier,width,height,note=f'{tier}p'+('60' if fps==60 else ''),fps=fps))[0]
    assert result.label==label
    assert result.semantic_height==tier and (result.width,result.height,result.fps)==(width,height,fps)
    assert result.semantic_quality_source=='youtube-format-note'


def test_youtube_portrait_keeps_1080p_vertical():
    result=options(video(1080,1080,1920))[0]
    assert result.label=='1080p 竖屏' and result.display_height==1080
    assert (result.width,result.height)==(1080,1920)


@pytest.mark.parametrize('note', ['1080p60','1080p60 HDR','1080p60, Premium, web', 'English, 1080p60'])
def test_youtube_fps_suffix_preserved(note):
    result=options(video(1080,1920,960,note=note,fps=None))[0]
    assert result.label=='1080p 60 FPS' and result.display_fps==60 and result.fps is None


def test_youtube_format_fallback_and_ambiguous_notes():
    result=options(video(1080,1920,960,note='',format='v - 1920x960 (1080p60)'))[0]
    assert result.label=='1080p 60 FPS' and result.semantic_quality_source=='youtube-format'
    for note in ('unknown','1080px','11080p','1080p / 720p'):
        result=options(video(1080,1920,960,note=note))[0]
        assert result.display_height==960 and result.semantic_height is None
    result=options(video(1080,1920,960,note='',quality=9))[0]
    assert result.display_height==960  # numeric quality is an extractor rank, not pixels


def test_youtube_semantic_grouping_retains_codec_candidates_and_raw_dimensions():
    formats=[video(1080,1920,960,note='1080p60',fps=59.94),
             video(1080,1920,958,note='1080p60',fps=60,)]
    formats[1].update(format_id='av1',vcodec='av01')
    result=options(*formats)
    assert len(result)==1 and set(result[0].candidate_video_format_ids)=={'v1080','av1'}
    assert result[0].label=='1080p 60 FPS'
    av1=apply_codec_preference(result[0],CodecPreference.AV1)
    assert (av1.width,av1.height,av1.fps)==(1920,958,60)
    assert av1.display_height==1080 and av1.label==result[0].label


def test_youtube_hdr_and_orientation_do_not_collapse():
    base=video(1080,1920,960)
    hdr={**base,'format_id':'hdr','dynamic_range':'HDR10'}
    portrait={**base,'format_id':'portrait','width':1080,'height':1920}
    result=options(base,hdr,portrait)
    assert {o.label for o in result}=={'1080p','1080p HDR','1080p 竖屏'}


def test_youtube_dynamic_range_aliases_collapse_without_hiding_distinct_ranges():
    raw=[{**video(1080,1920,960),'format_id':str(i),'dynamic_range':dr}
         for i,dr in enumerate(('SDR',None,'HDR','HDR10','HDR10+','HLG','DV'))]
    result=options(*raw)
    assert {o.label for o in result}=={'1080p','1080p HDR','1080p HDR10+','1080p HLG','1080p 杜比视界'}
    fallback=options(video(1080,1920,960,note='',dynamic_range='SDR'),
                     {**video(1080,1920,960,note='',dynamic_range='HDR10'),'format_id':'hdr'})
    assert {o.label for o in fallback}=={'960p','960p HDR'}


@pytest.mark.parametrize('cap', [2160,1440,1080,720])
def test_youtube_playlist_cap_semantic(cap):
    result=options(*(video(t,w,h) for t,w,h in
                     [(2160,3840,1920),(1440,2560,1280),(1080,1920,960),(720,1280,640)]))
    selected=choose_quality(result,f'cap:{cap}p')
    assert selected.display_height==cap
    assert choose_quality(result,'highest').display_height==2160
    assert choose_quality(result,'recommended').display_height==1080


def test_youtube_playlist_mixed_aspect_ratios():
    children=[[(2160,3840,2160),(1080,1920,1080)],
              [(2160,3840,1920),(1080,1920,960)], [(1080,1920,1080)],
              [(720,1280,720)], [(1080,1080,1920),(720,720,1280)]]
    for child,expected in zip(children,[1080,1080,1080,720,1080]):
        result=options(*(video(*f) for f in child))
        assert choose_quality(result,'cap:1080p').display_height==expected


@pytest.mark.parametrize('extractor',['Generic','Douyin','HuyaVideo','AfreecaTV'])
def test_generic_raw_dimension_fallback(extractor):
    result=options(video(2160,3840,1920),extractor=extractor)[0]
    assert result.label=='1920p 2K' and result.semantic_height is None
    portrait=options(video(720,406,720),extractor=extractor)[0]
    assert portrait.label=='406p 竖屏'


def test_real_youtube_redacted_sample():
    raw=json.loads((Path(__file__).parent/'fixtures'/'youtube_8kIJ7QLTSRc_formats.json').read_text('utf-8'))
    result=normalize_formats(raw,extractor_key='Youtube')
    assert [o.label for o in result]==['2160p 4K 60 FPS','1440p 2K 60 FPS','1080p 60 FPS',
                                     '720p 60 FPS','480p','360p','240p','144p']
    assert len({o.label for o in result})==len(result)
    tier720=next(o for o in result if o.semantic_height==720)
    assert set(tier720.candidate_video_format_ids)=={'136','247','298','302','398'}
    assert tier720.display_fps==60 and tier720.video_format_id in {'298','302','398'}
    for o in result:
        raw_selected=next(f for f in raw if f['format_id']==o.video_format_id)
        assert (o.width,o.height,o.fps)==(raw_selected['width'],raw_selected['height'],raw_selected['fps'])


def test_soop_portrait_ffprobe_regression():
    raw={'format_id':'hls','protocol':'m3u8_native','ext':'mp4',
         '_display_probe':{'width':406,'height':720,'fps':30,'source':'ffprobe'}}
    result=options(raw,extractor='AfreecaTV')[0]
    assert result.label=='406p 竖屏'
    assert result.height is result.width is None
    assert result.display_height==406 and result.semantic_quality_source=='ffprobe'


def test_youtube_quality_popup_and_profile_keep_semantic_tier(quick_window,qapp):
    from conftest import find_item,run_frames,click_item
    from yt_downloader.services.media_metadata import resolve_metadata
    from yt_downloader.core.models import DownloadProfile
    raw=json.loads((Path(__file__).parent/'fixtures'/'youtube_8kIJ7QLTSRc_formats.json').read_text('utf-8'))
    media=resolve_metadata({'id':'8kIJ7QLTSRc','extractor_key':'Youtube','title':'2:1',
                            'formats':raw},'https://www.youtube.com/watch?v=8kIJ7QLTSRc')
    page=quick_window.download_page
    page.show_video(media,profile=DownloadProfile('qa','QA',quality_tier='1080p'))
    assert page.available_formats[page.state['formatIndex']].display_height==1080
    run_frames(qapp,120)
    combo=find_item(quick_window,'formatCombo')
    click_item(quick_window,combo);run_frames(qapp)
    assert find_item(quick_window,'popup-formatCombo').property('visible')
    assert '1080p 60 FPS' in page.state['formats'][page.state['formatIndex']]
    assert not quick_window.qml_warnings


def test_deferred_youtube_semantic_quality_reaches_task_history_and_archive(qapp,tmp_path,monkeypatch):
    import threading
    from dataclasses import replace
    from test_download_service import _request, FakeYDL
    from yt_downloader.services.media_metadata import resolve_metadata
    from yt_downloader.services.download_service import DownloadService
    from yt_downloader.services.history_service import HistoryRepository
    from yt_downloader.core.models import HistoryRecord, TaskStatus
    from yt_downloader.services.archive_service import ArchiveRepository
    from yt_downloader.ui.quick_download import DownloadPresenter
    from types import SimpleNamespace
    raw=[video(2160,3840,1920),video(1440,2560,1280),video(1080,1920,960)]
    media=resolve_metadata({'id':'sample','title':'Source','extractor_key':'Youtube','formats':raw},
                           'https://www.youtube.com/watch?v=sample')
    class Resolver:
        def __init__(self,**_kwargs): pass
        def fetch_metadata(self,*_args,**_kwargs): return media
    monkeypatch.setattr('yt_downloader.services.media_resolver.MediaResolver',Resolver)
    request=replace(_request(tmp_path),resolve_before_download=True,batch_id='quality-audit',
                    preferred_quality='cap:1080p')
    page=DownloadPresenter(str(tmp_path),SimpleNamespace(add=lambda _: ''))
    page.add_task(request)
    result=DownloadService(ydl_factory=FakeYDL,require_tools=False,media_validator=lambda _:True).download(
        request,page.update_task,threading.Event())
    assert result.resolved_format.label=='1080p'
    assert result.resolved_format.height==960 and result.resolved_format.display_height==1080
    assert FakeYDL.last_options['format']=='v1080'
    assert page.tasks.get(0)['quality']=='1080p · MP4'
    archive=ArchiveRepository(tmp_path/'archive.db')
    assert archive.record_download(request,result)
    assert archive.lookup('Youtube',result.resolved_media.video_id).quality_label=='1080p'
    history=HistoryRepository(tmp_path/'history.db')
    history.upsert(HistoryRecord(request.task_id,media.video_id,media.url,media.title,result.file_path,
                                 request.format.label,result.file_size,None,TaskStatus.COMPLETED,'now'))
    history.update_media_identity(request.task_id,result.resolved_media,result.resolved_format)
    assert history.list_records()[0].quality_label=='1080p'

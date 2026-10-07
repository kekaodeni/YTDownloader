"""YouTube quality choices aggregate renditions without deleting candidates."""
from copy import deepcopy

import pytest

from yt_downloader.core.formats import normalize_formats, apply_codec_preference
from yt_downloader.core.models import CodecPreference
from yt_downloader.core.quality_target import choose_quality


def rendition(tier, fps, *, codec='avc1', bitrate=1000, portrait=False, **fields):
    return dict(format_id=f'{tier}-{fps}-{codec}', width=tier if portrait else tier * 2,
                height=tier * 2 if portrait else int(tier * 8 / 9), fps=fps,
                format_note=f'{tier}p' + ('60' if fps >= 50 else ''),
                vcodec=codec, acodec='mp4a', ext='mp4', tbr=bitrate, **fields)


@pytest.mark.parametrize('tier', [720, 1080])
def test_youtube_same_tier_prefers_high_fps(tier):
    # A high-bitrate AV1 low-FPS rendition must not outrank the high-FPS tier.
    low = rendition(tier, 29.97, codec='av01', bitrate=10000)
    high = rendition(tier, 59.94)
    result = normalize_formats([low, high], extractor_key='Youtube')
    assert len(result) == 1
    assert result[0].label == f'{tier}p 60 FPS'
    assert result[0].video_format_id == high['format_id']
    assert result[0].fps == 59.94


def test_youtube_same_tier_hides_lower_fps_option():
    result = normalize_formats([rendition(720, 29.97), rendition(720, 59.94)], extractor_key='Youtube')
    assert [o.label for o in result] == ['720p 60 FPS']


def test_youtube_lower_fps_candidate_preserved():
    raw = [rendition(720, fps, codec=codec) for fps in [29.97, 59.94]
           for codec in ['avc1', 'vp9', 'av01']]
    before = deepcopy(raw)
    option, = normalize_formats(raw, extractor_key='Youtube')
    assert raw == before
    assert set(option.candidate_video_format_ids) == {f['format_id'] for f in raw}
    for preference in CodecPreference:
        selected = apply_codec_preference(option, preference)
        assert selected.fps == 59.94 and selected.label == '720p 60 FPS'


@pytest.mark.parametrize('fps', [23.976, 24, 25, 29.97, 30])
def test_youtube_30fps_only_keeps_plain_quality(fps):
    raw = rendition(720, fps)
    option, = normalize_formats([raw], extractor_key='Youtube')
    assert option.label == '720p' and option.video_format_id == raw['format_id']


def test_youtube_playlist_cap_prefers_high_fps():
    low, high = rendition(720, 29.97), rendition(720, 59.94)
    raw = [rendition(1080, 60), low, high]
    option = choose_quality(normalize_formats(raw, extractor_key='Youtube'), 'cap:720p')
    assert option.label == '720p 60 FPS' and option.video_format_id == high['format_id']
    # A child whose fresh extraction no longer exposes 60 FPS retains its 30 FPS tier.
    fallback = choose_quality(normalize_formats([raw[0], low], extractor_key='Youtube'), 'cap:720p')
    assert fallback.label == '720p' and fallback.video_format_id == low['format_id']


def test_bilibili_fps_tiers_remain_separate():
    raw = [rendition(1080, fps, quality=qn) for qn, fps in [(80, 30), (112, 30), (116, 59.94)]]
    raw[1]['format_id'] += '-112'
    result = normalize_formats(raw, extractor_key='BiliBili')
    assert {o.label for o in result} == {'1080p', '1080p 高码率', '1080p 60 FPS'}


def test_youtube_portrait_high_fps_aggregates_without_losing_orientation():
    result = normalize_formats([rendition(1080, fps, portrait=True) for fps in [30, 59.94]],
                               extractor_key='Youtube')
    assert [o.label for o in result] == ['1080p 60 FPS 竖屏']
    assert (result[0].width, result[0].height) == (1080, 2160)


def test_youtube_sdr_hdr_remain_separate_with_lower_fps_candidates():
    raw = [rendition(2160, fps, dynamic_range=dr) for fps in [30, 60] for dr in ['SDR', 'HDR10']]
    for f in raw:
        f['format_id'] += '-' + f['dynamic_range']
    result = normalize_formats(raw, extractor_key='Youtube')
    assert {o.label for o in result} == {'2160p 4K 60 FPS', '2160p 4K 60 FPS HDR'}
    assert all(len(o.candidate_video_format_ids) == 2 for o in result)


def test_youtube_codec_preference_does_not_select_low_fps_when_high_fps_exists():
    option, = normalize_formats([rendition(720, 30, codec='av01'), rendition(720, 60)],
                                extractor_key='Youtube')
    selected = apply_codec_preference(option, CodecPreference.AV1)
    assert selected.label == '720p 60 FPS' and selected.fps == 60
    assert len(selected.candidate_video_format_ids) == 2


def test_youtube_missing_semantic_tier_keeps_existing_physical_fps_groups():
    raw = [rendition(720, fps) for fps in [30, 60]]
    for f in raw:
        f['format_note'] = ''
    result = normalize_formats(raw, extractor_key='Youtube')
    assert {o.label for o in result} == {'640p', '640p 60 FPS'}


def test_youtube_distinct_semantic_tiers_include_144p_without_cropping():
    raw = [rendition(144, 30), rendition(240, 30), rendition(720, 60)]
    before = deepcopy(raw)
    result = normalize_formats(raw, extractor_key='Youtube')
    assert [o.label for o in result] == ['720p 60 FPS', '240p', '144p']
    assert raw == before and raw[0]['format_note'] == '144p'
    # A genuinely low-resolution-only source still has a downloadable choice.
    low_only, = normalize_formats(raw[:1], extractor_key='Youtube')
    assert low_only.label == '144p'
    # Other sites keep their existing physical grouping.
    generic = [{**f, 'height': tier} for f, tier in zip(raw, [144, 240, 720])]
    assert len(normalize_formats(generic, extractor_key='Generic')) == 3

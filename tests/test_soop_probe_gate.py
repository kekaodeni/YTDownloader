"""SOOP's SDR flag is not a substitute for physical display dimensions."""
from contextlib import AbstractContextManager
from copy import deepcopy

import pytest

from yt_downloader.services.media_resolver import MediaResolver


URL = 'https://vod.sooplive.com/player/207147181/catch'


def stream(**values):
    return dict(format_id='hls', url='https://media.example/stream.m3u8',
                protocol='m3u8_native', ext='mp4', width=None, height=None,
                fps=None, vcodec=None, acodec=None, dynamic_range='SDR', **values)


def resolve(formats, probe, *, extractor='AfreecaTV', kind='video'):
    info = dict(extractor_key=extractor, _type=kind, formats=formats)
    before = deepcopy(info)
    class Ydl(AbstractContextManager):
        def __init__(self, _options): pass
        def __exit__(self, *_args): pass
        def extract_info(self, _url, *, download): return info
        def sanitize_info(self, value): return value
    resolver = MediaResolver(ydl_factory=Ydl, ffmpeg_service=probe, require_deno=False)
    media = resolver.fetch_metadata(URL, include_thumbnail=False, require_formats=False)
    assert info == before
    return media, resolver


class Probe:
    def __init__(self, result=None, error=None):
        self.result = result or dict(width=406, height=720, fps=24)
        self.error = error
        self.calls = []

    def probe_stream(self, url, *, http_headers, timeout):
        self.calls.append((url, http_headers, timeout))
        if self.error: raise self.error
        return self.result


def test_soop_sdr_missing_dimensions_probes_once_preserving_raw_fields():
    raw = stream()
    raw['http_headers'] = {'Referer': URL, 'Cookie': 'never-forward', 'Authorization': 'never-forward'}
    probe = Probe()
    media, resolver = resolve([raw], probe)
    resolver.fetch_metadata(URL, include_thumbnail=False)
    assert probe.calls == [(raw['url'], {'Referer': URL}, 8)]
    option = media.formats[0]
    assert option.label == '406p 竖屏'
    assert option.width is option.height is option.fps is None
    assert (option.detected_width, option.detected_height) == (406, 720)
    assert option.display_metadata_source == option.semantic_quality_source == 'ffprobe'


@pytest.mark.parametrize('error', [TimeoutError('bounded timeout'), OSError('unavailable'), ValueError('invalid JSON')])
def test_soop_sdr_probe_failure_returns_original_quality(error):
    probe = Probe(error=error)
    media, _ = resolve([stream()], probe)
    assert len(probe.calls) == 1 and probe.calls[0][2] == 8
    assert media.formats[0].label == '原始画质'
    assert media.formats[0].display_metadata_source == 'original'


def test_soop_sdr_invalid_probe_dimensions_return_original_quality():
    probe = Probe(result={'width': 0, 'height': 720})
    media, _ = resolve([stream()], probe)
    assert len(probe.calls) == 1 and media.formats[0].label == '原始画质'


def test_soop_existing_dimensions_not_probed():
    probe = Probe()
    raw = {**stream(), 'width': 406, 'height': 720, 'vcodec': 'avc1'}
    media, _ = resolve([raw], probe)
    assert not probe.calls and media.formats[0].label == '406p 竖屏'


@pytest.mark.parametrize('missing', ['width', 'height'])
def test_soop_one_missing_dimension_still_probes(missing):
    probe = Probe()
    raw = {**stream(), 'width': 406, 'height': 720, 'vcodec': 'avc1'}
    raw[missing] = None
    media, _ = resolve([raw], probe)
    assert len(probe.calls) == 1 and media.formats[0].label == '406p 竖屏'


def test_soop_multiple_unknown_variants_not_probed():
    probe = Probe()
    resolve([stream(), {**stream(), 'format_id': 'second'}], probe)
    assert not probe.calls


def test_soop_known_plus_unknown_variant_not_probed():
    probe = Probe()
    resolve([stream(), {**stream(), 'format_id': 'known', 'width': 1280, 'height': 720, 'vcodec': 'avc1'}], probe)
    assert not probe.calls


def test_soop_audio_only_and_playlist_not_probed():
    for formats, kind in [([{**stream(), 'vcodec': 'none', 'acodec': 'opus'}], 'video'),
                          ([stream()], 'playlist')]:
        probe = Probe()
        resolve(formats, probe, kind=kind)
        assert not probe.calls


@pytest.mark.parametrize('extractor', ['Youtube', 'BiliBili', 'Generic'])
def test_other_extractors_probe_contract_not_changed(extractor):
    probe = Probe()
    raw = {**stream(), 'vcodec': 'avc1', 'format_note': '1080p', 'quality': 80}
    resolve([raw], probe, extractor=extractor)
    assert not probe.calls

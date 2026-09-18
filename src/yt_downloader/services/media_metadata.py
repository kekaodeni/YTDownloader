"""Translate extractor dictionaries to the application's typed media contract."""
import math
from collections.abc import Mapping

from yt_downloader.core.formats import normalize_formats, normalize_audio_formats
from yt_downloader.core.models import CodecPreference, PlaylistMetadata, ResolvedMedia, SubtitleTrack
from yt_downloader.core.url import InvalidMediaUrl, normalize_media_url


# Reference integrations, not an input allowlist. Network smoke is reported separately.
VERIFIED_EXTRACTORS = frozenset({'youtube', 'bilibili', 'vimeo'})


def _http_url(value):
    try:
        return normalize_media_url(value) if isinstance(value, str) else None
    except InvalidMediaUrl:
        return None


def _number(value):
    return float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _tracks(value):
    if not isinstance(value, Mapping):
        return ()
    return tuple(SubtitleTrack(str(language), str(item.get('ext') or ''), url, str(item.get('name') or ''))
                 for language, items in value.items() if isinstance(items, list)
                 for item in items if isinstance(item, Mapping) and (url := _http_url(item.get('url'))))


def resolve_metadata(info, original_url, codec_preference=CodecPreference.AUTO):
    if not isinstance(info, Mapping):
        raise TypeError('yt-dlp returned non-mapping metadata')
    extractor = str(info.get('extractor') or '')
    extractor_key = str(info.get('extractor_key') or extractor)
    kind = info.get('_type')
    is_playlist = kind in {'playlist', 'multi_video'}
    duration = _number(info.get('duration'))
    raw_formats = info.get('formats')
    if not isinstance(raw_formats, list):
        raw_formats = [info] if info.get('url') and not is_playlist else []
    formats = () if is_playlist else tuple(normalize_formats(
        [item for item in raw_formats if isinstance(item, Mapping) and not item.get('has_drm')],
        duration=duration, codec_preference=codec_preference))
    usable = [item for item in raw_formats if isinstance(item, Mapping) and not item.get('has_drm')]
    audios = tuple(normalize_audio_formats(usable)) if not is_playlist else ()
    videos = tuple(normalize_formats([item for item in usable if item.get('acodec') == 'none'],
                                    duration=duration, codec_preference=codec_preference)) if not is_playlist else ()
    media_type = 'playlist' if is_playlist else 'live' if info.get('is_live') else 'audio' if info.get('vcodec') == 'none' else 'video'
    playlist = None
    if is_playlist or any(info.get(name) is not None for name in ('playlist_id', 'playlist_title', 'playlist_index')):
        index = _number(info.get('playlist_index'))
        count = _number(info.get('playlist_count'))
        playlist = PlaylistMetadata(str(info.get('id' if is_playlist else 'playlist_id') or ''),
                                    str(info.get('title' if is_playlist else 'playlist_title') or ''),
                                    int(index) if index is not None else None,
                                    int(count) if count is not None else None)
    thumbnail = _http_url(info.get('thumbnail'))
    if not thumbnail and isinstance(info.get('thumbnails'), list):
        thumbnail = next((_http_url(item.get('url')) for item in reversed(info['thumbnails'])
                          if isinstance(item, Mapping) and _http_url(item.get('url'))), None)
    webpage_url = _http_url(info.get('webpage_url')) or original_url
    return ResolvedMedia(
        # Replay the successful extractor input for downloads/history retries.
        # Canonical webpage_url can have different access requirements.
        video_id=str(info.get('id') or ''), url=original_url,
        title=str(info.get('title') or '未命名媒体'),
        channel=str(info.get('channel') or info.get('uploader') or '未知作者'),
        duration=duration, thumbnail_url=thumbnail, thumbnail_bytes=None, formats=formats,
        audio_formats=audios, video_only_formats=videos,
        extractor=extractor, extractor_key=extractor_key, original_url=original_url,
        webpage_url=webpage_url, media_type=media_type, uploader=str(info.get('uploader') or ''),
        upload_date=str(info['upload_date']) if info.get('upload_date') else None,
        description=str(info.get('description') or ''), subtitles=_tracks(info.get('subtitles')),
        automatic_captions=_tracks(info.get('automatic_captions')), playlist=playlist,
        compatibility='VERIFIED' if extractor_key.casefold() in VERIFIED_EXTRACTORS or extractor.casefold() in VERIFIED_EXTRACTORS else 'EXPERIMENTAL',
    )

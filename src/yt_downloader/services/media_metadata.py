"""Translate extractor dictionaries to the application's typed media contract."""
import math
from collections.abc import Mapping

from yt_downloader.core.formats import normalize_formats, normalize_audio_formats
from yt_downloader.core.models import (Collection, CollectionQualityMode, MediaChapter, PlaylistEntry,
                                       PlaylistMetadata, ResolvedMedia, SubtitleTrack, ThumbnailOption)
from yt_downloader.core.url import InvalidMediaUrl, normalize_media_url


# Reference integrations, not an input allowlist. Network smoke is reported separately.
METADATA_VERIFIED_EXTRACTORS = frozenset({'youtube', 'bilibili', 'vimeo'})
DOWNLOAD_VERIFIED_EXTRACTORS = frozenset({'youtube', 'bilibili'})


def _http_url(value):
    try:
        return normalize_media_url(value) if isinstance(value, str) else None
    except InvalidMediaUrl:
        return None


def _number(value):
    return float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def thumbnail_url(info):
    """Prefer the extractor's primary image, then the largest valid candidate."""
    primary = _http_url(info.get('thumbnail'))
    if primary:
        return primary
    candidates = [item for item in info.get('thumbnails') or []
                  if isinstance(item, Mapping) and _http_url(item.get('url'))]
    best = max(enumerate(candidates),
               key=lambda pair: ((_number(pair[1].get('width')) or 0) * (_number(pair[1].get('height')) or 1),
                                 pair[0]), default=None)
    return _http_url(best[1]['url']) if best else None


def _tracks(value, is_auto=False):
    if not isinstance(value, Mapping):
        return ()
    return tuple(SubtitleTrack(str(language), str(item.get('ext') or ''), _http_url(item.get('url')) or '',
                               str(item.get('name') or ''), is_auto, str(item.get('data') or ''))
                 for language, items in value.items() if isinstance(items, list)
                 for item in items if isinstance(item, Mapping) and
                 (_http_url(item.get('url')) or (isinstance(item.get('data'), str) and item['data'])))


def _thumbnails(info):
    candidates = {}
    for item in info.get('thumbnails') or ():
        if not isinstance(item, Mapping) or not (url := _http_url(item.get('url'))):
            continue
        width, height = _number(item.get('width')), _number(item.get('height'))
        candidates[url] = ThumbnailOption(url, int(width) if width else None,
                                         int(height) if height else None, _number(item.get('preference')) or 0)
    if primary := _http_url(info.get('thumbnail')):
        candidates.setdefault(primary, ThumbnailOption(primary))
    return tuple(candidates.values())


def _chapters(value):
    """Keep semantic chapters in task/IPC snapshots, without extractor payloads."""
    if not isinstance(value, (list, tuple)):
        return ()
    chapters = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        start, end = _number(item.get('start_time')), _number(item.get('end_time'))
        if start is None or (item.get('end_time') is not None and (end is None or end <= start)):
            continue
        chapters.append(MediaChapter(start, end, str(item.get('title') or '')))
    return tuple(chapters)


def resolve_metadata(info, original_url, *, requested_url=None, detected_formats=None, cookie_used=False):
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
    detected_formats = detected_formats or {}
    display_formats = []
    for item in raw_formats:
        if not isinstance(item, Mapping) or item.get('has_drm'):
            continue
        copy = dict(item)
        detected = detected_formats.get(str(copy.get('format_id') or ''))
        if detected:
            copy['_display_probe'] = detected
        display_formats.append(copy)
    formats = () if is_playlist else tuple(normalize_formats(
        display_formats,
        duration=duration, extractor_key=extractor_key))
    # A separately resolved watch video can seed a task, but it cannot stand in
    # for a deferred playlist's per-entry quality capabilities.
    collection_quality_formats = ()
    usable = display_formats
    audios = tuple(normalize_audio_formats(usable)) if not is_playlist else ()
    videos = tuple(normalize_formats([item for item in usable if item.get('acodec') == 'none'],
                                    duration=duration,
                                    extractor_key=extractor_key)) if not is_playlist else ()
    raw_entries = list((info.get('entries') or [])[:1000]) if is_playlist else []
    is_bilibili = extractor_key.casefold().startswith('bilibili') or extractor.casefold().startswith('bilibili')
    has_embedded_entries = is_bilibili and any(
        isinstance(item, Mapping) and isinstance(item.get('formats'), list) and item.get('formats')
        for item in raw_entries)
    media_type = ('multi_video' if kind == 'multi_video' or has_embedded_entries else 'playlist') if is_playlist else 'live' if info.get('is_live') else 'audio' if info.get('vcodec') == 'none' else 'video'
    playlist = None
    if is_playlist or any(info.get(name) is not None for name in ('playlist_id', 'playlist_title', 'playlist_index')):
        index = _number(info.get('playlist_index'))
        count = _number(info.get('playlist_count'))
        playlist = PlaylistMetadata(str(info.get('id' if is_playlist else 'playlist_id') or ''),
                                    str(info.get('title' if is_playlist else 'playlist_title') or ''),
                                    int(index) if index is not None else None,
                                    int(count) if count is not None else None)
    reference = info.get('_collection_reference') or {}
    thumbnail = thumbnail_url(info)
    if not thumbnail and isinstance(reference, Mapping):
        thumbnail = thumbnail_url(reference)
    if not thumbnail and (has_embedded_entries or extractor_key.casefold() in {'bilibilibangumiseason', 'bilibilibangumimedia'}):
        thumbnail = next((image for item in raw_entries if isinstance(item, Mapping)
                          and item.get('availability') not in {'private', 'premium_only', 'subscriber_only'}
                          and (image := thumbnail_url(item))), None)
    webpage_url = _http_url(info.get('webpage_url')) or original_url
    entries = []
    if is_playlist:
        for index, item in enumerate(raw_entries, 1):
            item = item if isinstance(item, Mapping) else {}
            embedded_raw = [value for value in (item.get('formats') or [])
                            if isinstance(value, Mapping) and not value.get('has_drm')]
            url = '' if embedded_raw else (_http_url(item.get('webpage_url')) or _http_url(item.get('url')) or '')
            entry_duration = _number(item.get('duration'))
            entry_key = str(item.get('ie_key') or item.get('extractor_key') or extractor_key)
            entry_formats = tuple(normalize_formats(embedded_raw, duration=entry_duration,
                                                   extractor_key=entry_key)) if embedded_raw else ()
            entry_audio = tuple(normalize_audio_formats(embedded_raw)) if embedded_raw else ()
            entry_video_only = tuple(normalize_formats([value for value in embedded_raw
                                                        if value.get('acodec') == 'none'],
                                                       duration=entry_duration,
                                                       extractor_key=entry_key)) if embedded_raw else ()
            item_thumbnail = thumbnail_url(item)
            entry_index = _number(item.get('playlist_index')) or index
            has_usable_embedded = bool(entry_formats or entry_audio or entry_video_only)
            entries.append(PlaylistEntry(str(item.get('id') or index), int(entry_index),
                          str(item.get('title') or '未命名媒体'), url,
                          str(item.get('ie_key') or item.get('extractor_key') or extractor_key),
                          entry_duration, item_thumbnail or '',
                          not bool(url or has_usable_embedded) or item.get('availability') in {'private', 'premium_only', 'subscriber_only', 'needs_auth'},
                          entry_formats, entry_audio, entry_video_only, has_usable_embedded,
                          chapters=_chapters(item.get('chapters')), availability=str(item.get('availability') or ''),
                          title_missing=not bool(item.get('title'))))
    selectable_entries = [entry for entry in entries if not entry.unavailable]
    resolved_collection = bool(selectable_entries) and all(entry.formats for entry in selectable_entries)
    collection_quality_mode = (CollectionQualityMode.RESOLVED_COMMON_FORMATS if resolved_collection
                               else CollectionQualityMode.DEFERRED_BATCH_TARGET) if is_playlist else ''
    if is_playlist and resolved_collection:
        labels_by_entry = [{option.label for option in entry.formats} for entry in selectable_entries]
        common_labels = set.intersection(*labels_by_entry) if labels_by_entry else set()
        # Keep a representative option for each semantic label; children map
        # the chosen label to their own native candidates at enqueue time.
        collection_quality_formats = tuple(option for option in selectable_entries[0].formats
                                           if option.label in common_labels)
    elif (is_playlist and extractor_key.casefold() in {'bilibilibangumiseason', 'bilibilibangumimedia'}
          and isinstance(reference, Mapping)):
        collection_quality_formats = tuple(normalize_formats(
            [item for item in reference.get('formats') or []
             if isinstance(item, Mapping) and not item.get('has_drm')],
            duration=_number(reference.get('duration')),
            extractor_key=str(reference.get('extractor_key') or 'BiliBiliBangumi')))
        if collection_quality_formats:
            collection_quality_mode = CollectionQualityMode.REFERENCE_EPISODE_FORMATS
    metadata_compatibility = 'VERIFIED' if extractor_key.casefold() in METADATA_VERIFIED_EXTRACTORS or extractor.casefold() in METADATA_VERIFIED_EXTRACTORS else 'EXPERIMENTAL'
    download_compatibility = 'VERIFIED' if extractor_key.casefold() in DOWNLOAD_VERIFIED_EXTRACTORS or extractor.casefold() in DOWNLOAD_VERIFIED_EXTRACTORS else 'EXPERIMENTAL'
    entries_truncated = is_playlist and len(info.get("entries") or []) > 1000
    collection = Collection(media_type, tuple(entries), entries_truncated) if is_playlist else None
    return ResolvedMedia(
        # Replay the successful extractor input for downloads/history retries.
        # Canonical webpage_url can have different access requirements.
        video_id=str(info.get('id') or ''), url=original_url,
        title=str(info.get('title') or '未命名媒体'),
        channel=str(info.get('channel') or info.get('uploader') or '未知作者'),
        duration=duration, thumbnail_url=thumbnail, thumbnail_bytes=None, formats=formats,
        audio_formats=audios, video_only_formats=videos, entries=tuple(entries),
        entries_truncated=entries_truncated, collection=collection,
        extractor=extractor, extractor_key=extractor_key, original_url=requested_url or original_url,
        webpage_url=webpage_url, media_type=media_type, uploader=str(info.get('uploader') or ''),
        upload_date=str(info['upload_date']) if info.get('upload_date') else None,
        description=str(info.get('description') or ''), subtitles=_tracks(info.get('subtitles')),
        automatic_captions=_tracks(info.get('automatic_captions'), True), playlist=playlist,
        compatibility=download_compatibility,
        metadata_compatibility=metadata_compatibility,
        download_compatibility=download_compatibility,
        collection_quality_formats=collection_quality_formats,
        collection_quality_mode=collection_quality_mode,
        cookie_used=bool(cookie_used),
        chapters=_chapters(info.get('chapters')),
        thumbnails=_thumbnails(info),
    )

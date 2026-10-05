"""Lightweight Season presentation enrichment, with one native quality reference.

The bundled flat extractor drops titles/covers from Bilibili's episode index.
Keep download entries deferred: the reference is a capability sample, never a
replacement for the children's own extraction or native format selection.
"""
from collections.abc import Mapping
import json
import logging
import re
from urllib.parse import parse_qs, urlsplit

from yt_dlp.networking.common import Request

from yt_downloader.core.errors import ErrorContext, OperationCancelled
from yt_downloader.services.media_metadata import thumbnail_url

logger = logging.getLogger(__name__)
_SEASON_KEYS = {'bilibilibangumiseason', 'bilibilibangumimedia'}


def enrich_season(ydl, info, url, cancel_event=None):
    """Use the existing authenticated yt-dlp session for both bounded requests."""
    if (not isinstance(info, Mapping) or info.get('_type') != 'playlist'
            or str(info.get('extractor_key') or info.get('extractor') or '').casefold() not in _SEASON_KEYS):
        return info

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise OperationCancelled(ErrorContext(url=url, stage='Fetching metadata'))

    info = dict(info)
    entries = [dict(entry) if isinstance(entry, Mapping) else entry for entry in info.get('entries') or []]
    info['entries'] = entries
    valid = [entry for entry in entries if isinstance(entry, Mapping)
             and re.fullmatch(r'https?://www\.bilibili\.com/bangumi/play/ep\d+(?:[?#].*)?',
                              str(entry.get('webpage_url') or entry.get('url') or ''))
             and entry.get('availability') not in {'private', 'premium_only', 'subscriber_only'}]
    if not valid:
        return info
    parsed = urlsplit(url)
    season_id = re.search(r'/ss(\d+)', parsed.path)
    episode_id = re.search(r'/ep(\d+)', valid[0].get('webpage_url') or valid[0]['url'])[1]
    parameter = f'season_id={season_id[1]}' if season_id else f'ep_id={episode_id}'
    response = None
    check_cancel()
    try:
        response = ydl.urlopen(Request('https://api.bilibili.com/pgc/view/web/season?' + parameter,
                                       headers={'Referer': url}, extensions={'timeout': 8.0}))
        payload = json.loads(response.read())
        data = payload.get('result') if isinstance(payload, Mapping) and payload.get('code') == 0 else None
        if isinstance(data, Mapping):
            if not thumbnail_url(info) and data.get('cover'):
                info['thumbnail'] = data['cover']
            if not info.get('description') and data.get('evaluate'):
                info['description'] = data['evaluate']
            info['season_id'] = data.get('season_id')
            by_id = {str(episode.get('id')): episode for episode in data.get('episodes') or []
                     if isinstance(episode, Mapping)}
            for entry in valid:
                episode = by_id.get(str(entry.get('id')))
                if not episode:
                    continue
                if not entry.get('title'):
                    entry['title'] = ' '.join(str(episode.get(key) or '').strip()
                                             for key in ('title', 'long_title')).strip()
                if not thumbnail_url(entry):
                    entry['thumbnail'] = episode.get('cover') or thumbnail_url(info)
                if entry.get('duration') is None and isinstance(episode.get('duration'), (int, float)):
                    entry['duration'] = episode['duration'] / 1000
                entry['episode_number'] = episode.get('title')
                # VIP badges and the site's allow_download flag are not evidence
                # that the current authenticated extractor cannot play a child.
    except OperationCancelled:
        raise
    except Exception as error:
        # Optional index enrichment must not erase an otherwise usable playlist.
        # Log only the class: HTTP errors can contain authenticated URLs.
        logger.warning('Bangumi episode index unavailable (%s)', type(error).__name__)
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
    check_cancel()
    current_id = (re.search(r'/ep(\d+)', parsed.path) or [None, None])[1]
    current_id = current_id or (parse_qs(parsed.query).get('ep_id') or [None])[0]
    candidates = sorted(valid, key=lambda entry: str(entry.get('id')) != str(current_id))
    # At most three attempts when initial episodes are inaccessible. Never
    # enumerate all children's formats merely to populate the toolbar.
    for entry in candidates[:3]:
        check_cancel()
        try:
            reference = ydl.extract_info(entry.get('webpage_url') or entry['url'], download=False)
            check_cancel()
            if not isinstance(reference, Mapping) or reference.get('_type') in {'playlist', 'multi_video'}:
                continue
            if not any(isinstance(item, Mapping) and not item.get('has_drm') and item.get('vcodec') != 'none'
                       for item in reference.get('formats') or []):
                continue
            reference = dict(reference)
            # Native Bangumi's thumbnail is a season square cover. Prefer the
            # authoritative episode cover supplied by the lightweight index.
            reference['thumbnail'] = thumbnail_url(entry) or thumbnail_url(reference)
            info['_collection_reference'] = reference
            break
        except OperationCancelled:
            raise
        except Exception as error:
            logger.warning('Bangumi reference unavailable (%s)', type(error).__name__)
    check_cancel()
    return info

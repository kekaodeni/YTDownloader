"""Small semantic target policy shared by collection children."""

from __future__ import annotations

import re


def choose_quality(options, target):
    """Resolve a collection's global quality target against one item's formats.

    Prefer an exact label. For a resolution target, fall back to the best semantic
    option at or below the target, then the lowest available option if the source
    has no option at/below the requested ceiling.
    """
    options = tuple(options)
    if not options:
        return None
    target = str(target or 'recommended')
    semantic = re.fullmatch(r'bilibili:(\d+)', target)
    if semantic:
        from .formats import bilibili_quality_rank
        rank = bilibili_quality_rank(int(semantic[1]))
        if rank is not None:
            known = [item for item in options if bilibili_quality_rank(item.site_quality) is not None]
            eligible = [item for item in known if item.quality_rank <= rank]
            key = lambda item: (item.quality_rank, item.quality_sort_key)
            if eligible:
                return max(eligible, key=key)
            if known:
                return min(known, key=key)
    if target in {'recommended', '自动推荐'}:
        return next((item for item in options if item.is_recommended), options[0])
    if target in {'highest', '最高质量'}:
        return max(options, key=lambda item: item.quality_sort_key)
    is_cap = target.startswith('cap:')
    resolution_target = target[4:] if is_cap else target
    exact = next((item for item in options if item.label == target), None)
    if exact and not is_cap:
        return exact
    match = re.search(r'(?<!\d)(\d{3,4})\s*p', resolution_target, re.I)
    if not match:
        return next((item for item in options if item.is_recommended), options[0])
    ceiling = int(match.group(1))
    eligible = [item for item in options if item.display_height is not None and item.display_height <= ceiling]
    return max(eligible, key=lambda item: item.quality_sort_key) if eligible else min(options, key=lambda item: item.quality_sort_key)

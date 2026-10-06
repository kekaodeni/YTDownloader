"""Preserve the Collection row's cover through native yt-dlp thumbnail IO."""
from yt_dlp.postprocessor.common import PostProcessor


class CollectionCoverPP(PostProcessor):
    def __init__(self, downloader, canonical_url, parent_url):
        super().__init__(downloader)
        self.canonical_url, self.parent_url = canonical_url, parent_url

    def run(self, info):
        # yt-dlp downloads from the end of this list, falling back on network
        # failure. Run at `video`, BEFORE _write_thumbnails (before_dl is too late).
        candidates = []
        def append(url, thumbnail=None):
            if not url:
                return
            candidates[:] = [item for item in candidates if item['url'] != url]
            candidates.append({**(thumbnail or {}), 'url': url,
                               'id': str(len(candidates)), 'filepath': None})
        append(self.parent_url)
        for thumbnail in info.get('thumbnails') or ():
            append(thumbnail.get('url'), thumbnail)
        append(info.get('thumbnail'))
        append(self.canonical_url)
        info['thumbnails'] = candidates
        info['thumbnail'] = candidates[-1]['url'] if candidates else None
        return [], info

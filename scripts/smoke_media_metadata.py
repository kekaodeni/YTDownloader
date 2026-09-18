"""Small anonymous public metadata smoke; never downloads media files."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import yt_dlp.version

from yt_downloader.core.errors import AppError
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.media_resolver import MediaResolver
from yt_downloader.services.network_policy import NetworkPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True, choices=['youtube', 'bilibili', 'vimeo'])
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--proxy-mode', choices=['system', 'direct'], default='system')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new report path for each attempt')
    report = dict(site=args.site, url=redact_sensitive(args.url),
                  checked_at=datetime.now(timezone.utc).isoformat(), yt_dlp=yt_dlp.version.__version__,
                  proxy_mode=args.proxy_mode, status='FAIL')
    resolver = MediaResolver(network_policy=NetworkPolicy(args.proxy_mode))
    try:
        media = resolver.fetch_metadata(args.url)
        report.update(extractor=media.extractor, title=media.title, duration=media.duration,
                      formats=len(media.formats), thumbnail_url=bool(media.thumbnail_url),
                      thumbnail_bytes=len(media.thumbnail_bytes or b''), media_type=media.media_type)
        if media.title and media.duration is not None and media.formats and media.thumbnail_bytes:
            report['status'] = 'PASS'
        else:
            report['reason'] = 'Missing one or more required basic metadata fields/thumbnail bytes'
    except AppError as error:
        report.update(code=error.code, reason=redact_sensitive(error.technical_message)[:1500])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

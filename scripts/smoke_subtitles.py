"""Anonymous metadata and one subtitle transfer; never downloads video/audio."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import threading

from yt_downloader.core.models import DownloadRequest
from yt_downloader.services.media_resolver import MediaResolver
from yt_downloader.services.subtitle_service import SubtitleService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--language', default='en')
    parser.add_argument('--automatic', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new report path')
    media = MediaResolver().fetch_metadata(args.url, include_thumbnail=False)
    with tempfile.TemporaryDirectory(prefix='ytd-subtitle-smoke-') as temporary:
        root = Path(temporary)
        request = DownloadRequest('subtitle-smoke', media, media.formats[0], root, 'fixture',
                                  subtitle_enabled=True, subtitle_languages=(args.language,),
                                  subtitle_auto=args.automatic)
        result = SubtitleService().process(request, root / 'unused.mp4', root, threading.Event())
        report = dict(status='PASS' if result.files and not result.warnings else 'FAIL',
                      language=args.language, automatic=result.auto_used, warnings=list(result.warnings),
                      files=[dict(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  format=path.suffix.lstrip('.')) for _, path in result.files])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

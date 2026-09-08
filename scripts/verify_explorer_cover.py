"""Read-only verification of embedded cover bytes and the Windows Shell thumbnail."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.infrastructure.windows_thumbnail import shell_thumbnail_matches
from yt_downloader.services.ffmpeg_service import FfmpegService

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/validation-current/cover-fixtures')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    service = FfmpegService(find_tool('ffmpeg'), find_tool('ffprobe'))
    reference = args.fixtures / 'reference.jpg'
    expected = hashlib.sha256(reference.read_bytes()).hexdigest()
    results = []
    for extension in ('mp4', 'm4v', 'mkv'):
        media = args.fixtures / ('blue-video-red-cover.' + extension)
        before = hashlib.sha256(media.read_bytes()).hexdigest()
        probe = service.probe(media)
        covers = [stream for stream in probe['streams'] if service._is_cover_stream(stream)]
        if len(covers) != 1:
            raise RuntimeError(f'{extension}: expected exactly one front cover')
        with tempfile.TemporaryDirectory(prefix='yt-cover-verify-') as temporary:
            extracted = Path(temporary) / 'cover.jpg'
            subprocess.run([str(find_tool('ffmpeg')), '-v', 'error', '-i', str(media), '-map', f"0:{covers[0]['index']}", '-c', 'copy', '-frames:v', '1', '-f', 'image2', str(extracted)], check=True, capture_output=True)
            actual = hashlib.sha256(extracted.read_bytes()).hexdigest()
        result = dict(extension=extension, embedded_bytes_match=actual == expected, shell_thumbnail_matches=shell_thumbnail_matches(media, reference), file_unchanged=before == hashlib.sha256(media.read_bytes()).hexdigest())
        results.append(result)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))
    return 0 if all(r['embedded_bytes_match'] and r['file_unchanged'] and r['shell_thumbnail_matches'] is True for r in results) else 2

if __name__ == '__main__':
    raise SystemExit(main())

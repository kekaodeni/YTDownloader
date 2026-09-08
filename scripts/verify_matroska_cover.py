"""Build independent MKVToolNix controls and compare real Matroska attachments."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from PIL import Image
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.infrastructure.windows_thumbnail import _shell_image, shell_thumbnail_matches
from yt_downloader.services.ffmpeg_service import FfmpegService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mkvtoolnix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    merge = (args.mkvtoolnix / 'mkvmerge.exe').resolve(strict=True)
    extract = (args.mkvtoolnix / 'mkvextract.exe').resolve(strict=True)
    def run(*arguments):
        return subprocess.run([str(a) for a in arguments], check=True, capture_output=True).stdout
    ffmpeg = find_tool('ffmpeg')
    service = FfmpegService(ffmpeg, find_tool('ffprobe'))
    source = output / 'blue-source.mkv'
    run(ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=blue:s=180x320:d=1:r=25', '-c:v', 'libx264', source)
    results = []
    for image_kind, suffix, mime in [('JPEG', 'jpg', 'image/jpeg'), ('PNG', 'png', 'image/png')]:
        cover = output / ('selected.' + suffix)
        Image.new('RGB', (180, 320), 'red').save(cover, image_kind)
        for writer in ('mkvtoolnix', 'ytdownloader'):
            media = output / (writer + '-' + suffix + '.mkv')
            if writer == 'mkvtoolnix':
                run(merge, '-o', media, source, '--attachment-name', 'cover.' + suffix,
                    '--attachment-mime-type', mime, '--attach-file', cover)
            else:
                shutil.copyfile(source, media)
                service.embed_cover(media, cover)
            identity = json.loads(run(merge, '-J', media))
            (output / (media.stem + '-structure.json')).write_text(json.dumps(identity, indent=2), encoding='utf-8')
            attachments = identity['attachments']
            assert len(attachments) == 1
            attachment = attachments[0]
            assert attachment['file_name'] == 'cover.' + suffix and attachment['content_type'] == mime
            extracted = output / (media.stem + '-extracted.' + suffix)
            run(extract, media, 'attachments', str(attachment['id']) + ':' + str(extracted))
            assert extracted.read_bytes() == cover.read_bytes()
            thumbnail = _shell_image(media)
            if thumbnail is not None:
                thumbnail.save(str(output / (media.stem + '-shell.png')))
            results.append(dict(writer=writer, image_kind=image_kind, media=media.name,
                                attachment_name=attachment['file_name'], mime=attachment['content_type'],
                                embedded_sha256=hashlib.sha256(extracted.read_bytes()).hexdigest(),
                                embedded_bytes_match=True, shell_match=shell_thumbnail_matches(media, cover)))
    report = dict(mkvtoolnix_version=run(merge, '--version').decode().strip(), results=results)
    (output / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if all(row['shell_match'] is True for row in results) else 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Explicit subtitle selection and optional processing, separate from media success."""
from dataclasses import dataclass
from pathlib import Path
import re

import yt_dlp
from yt_downloader.core.errors import OperationCancelled
from yt_downloader.services.ffmpeg_service import FfmpegService


@dataclass(frozen=True)
class SubtitleResult:
    media: Path
    files: tuple[tuple[str, Path], ...] = ()
    warnings: tuple[str, ...] = ()
    embedded: bool = False
    auto_used: bool = False


class SubtitleService:
    def __init__(self, ffmpeg_path=None, network_policy=None):
        self.ffmpeg = FfmpegService(ffmpeg_path=ffmpeg_path)
        self.network_policy = network_policy

    def process(self, request, media, workspace, cancel_event):
        tracks = select_tracks(request)
        if not tracks:
            return SubtitleResult(media, warnings=('媒体已保存，但所选语言没有可用字幕。',))
        files, warnings = [], []
        auto_used = False
        options = {'quiet': True, 'no_warnings': True, 'ignoreconfig': True, 'usenetrc': False,
                   'cachedir': False, 'socket_timeout': 15}
        if self.network_policy:
            options.update(self.network_policy.ytdlp_options())
        with yt_dlp.YoutubeDL(options) as ydl:
            for track in tracks:
                if cancel_event.is_set():
                    raise OperationCancelled()
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', track.language) or track.extension not in {'srt', 'vtt', 'ttml', 'dfxp', 'ass', 'ssa'}:
                    warnings.append(f'{language_name(track.language)}：字幕格式暂不支持。')
                    continue
                source = workspace / f'subtitle-{track.language}.{track.extension}'
                target = workspace / f'subtitle-{track.language}.{request.subtitle_format}'
                try:
                    with ydl.urlopen(track.url) as response, source.open('wb') as output:
                        size = 0
                        while chunk := response.read(65536):
                            if cancel_event.is_set():
                                raise OperationCancelled()
                            size += len(chunk)
                            if size > 16 * 1024 * 1024:
                                raise ValueError('Subtitle exceeds size limit')
                            output.write(chunk)
                    if size == 0:
                        raise ValueError('Empty subtitle response')
                    if source != target:
                        self.ffmpeg.convert_subtitle(source, target, cancel_event=cancel_event)
                    files.append((track.language, target))
                    auto_used |= track.is_auto
                except OperationCancelled:
                    raise
                except Exception:
                    warnings.append(f'{language_name(track.language)}：字幕下载或转换失败，媒体已保留。')
        if request.subtitle_embed and files:
            try:
                candidate = workspace / ('subtitled' + media.suffix)
                self.ffmpeg.embed_subtitles(media, files, candidate, cancel_event=cancel_event)
                return SubtitleResult(candidate, (), tuple(warnings), True, auto_used)
            except OperationCancelled:
                raise
            except Exception:
                # Explicit warning, never silently claim the requested embed succeeded.
                warnings.append('字幕嵌入失败；媒体已保留，字幕另存为独立文件。')
        return SubtitleResult(media, tuple(files), tuple(warnings), False, auto_used)


def language_name(code):
    return {'zh': '中文', 'zh-CN': '简体中文', 'zh-Hans': '简体中文',
            'zh-TW': '繁體中文', 'zh-Hant': '繁體中文', 'en': 'English',
            'en-US': 'English (US)', 'en-GB': 'English (UK)',
            'ja': '日本語', 'ko': '한국어'}.get(code, code)


def select_tracks(request):
    if not request.subtitle_enabled:
        return ()
    pool = (*request.video.subtitles, *(request.video.automatic_captions if request.subtitle_auto else ()))
    result = []
    for language in request.subtitle_languages:
        candidates = [track for track in pool if track.language == language]
        # Manual precedes automatic; prefer the requested format or convertible VTT/SRT.
        if candidates:
            manual = [track for track in candidates if not track.is_auto]
            candidates = manual or candidates
            rank = {request.subtitle_format: 0, 'vtt': 1, 'srt': 2, 'ttml': 3}
            result.append(min(candidates, key=lambda track: rank.get(track.extension, 10)))
    return tuple(result)

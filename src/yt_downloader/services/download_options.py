"""Translate a structured media request into yt-dlp stream selection."""
from dataclasses import replace
from yt_downloader.core.models import MediaMode


def prepare_request(request):
    """Derive the actual output and progress contract before any IO."""
    request = _effective_subtitle_request(request)
    mode = MediaMode(request.media_mode)
    if request.subtitle_format not in {'srt', 'vtt'}:
        raise ValueError('不支持的字幕格式')
    if request.subtitle_enabled and request.subtitle_embed and (mode is MediaMode.AUDIO_ONLY or request.format.final_ext not in {'mp4', 'mkv'}):
        raise ValueError('此模式或容器不支持嵌入字幕，请明确选择独立字幕文件。')
    option = request.format
    if mode is MediaMode.VIDEO_ONLY:
        if not option.audio_format_id and option.acodec != 'none':
            raise ValueError('该格式包含声音，请选择独立视频流。')
        ext = option.video_extension or option.final_ext
        option = replace(option, format_selector=option.video_format_id,
                         acodec='none', audio_format_id=None, requires_merge=False,
                         final_ext=ext, container=ext.upper(), estimated_size=option.video_size,
                         audio_size=None)
    elif mode is MediaMode.AUDIO_ONLY:
        if request.audio_codec not in {'original', 'm4a', 'mp3', 'opus', 'flac'}:
            raise ValueError('不支持的音频格式')
        if request.audio_quality not in {'original', '320', '256', '192', '128'}:
            raise ValueError('不支持的音频质量')
        audio_id = option.audio_format_id or (option.video_format_id if option.vcodec == 'none' else None)
        if not audio_id:
            raise ValueError('此媒体没有可独立下载的音频流。')
        source_ext = option.audio_extension or ('m4a' if option.acodec.startswith(('mp4a', 'aac')) else 'webm')
        ext = source_ext if request.audio_codec == 'original' else request.audio_codec
        option = replace(option, format_selector=audio_id, video_format_id=audio_id,
                         audio_format_id=None, vcodec='none', height=None, fps=None,
                         label=ext.upper() + ' · ' + ('Original' if request.audio_quality == 'original' else request.audio_quality + ' kbps'),
                         final_ext=ext, container=ext.upper(), requires_merge=False,
                         estimated_size=option.audio_size, video_size=option.audio_size,
                         audio_size=None, audio_extension=source_ext)
    return replace(request, media_mode=mode, format=option)


def _effective_subtitle_request(request):
    """Drop subtitle work that the resolved media cannot actually perform."""
    if not request.subtitle_enabled:
        return replace(request, subtitle_auto=False, subtitle_embed=False, subtitle_languages=())
    manual = tuple(request.video.subtitles)
    automatic = tuple(request.video.automatic_captions)
    if not manual and not automatic:
        return replace(request, subtitle_enabled=False, subtitle_auto=False,
                       subtitle_embed=False, subtitle_languages=())
    auto = bool(request.subtitle_auto or (automatic and not manual))
    tracks = (*manual, *(automatic if auto else ()))
    available = {track.language for track in tracks}
    languages = tuple(dict.fromkeys(code for code in request.subtitle_languages if code in available))
    if not languages:
        return replace(request, subtitle_enabled=False, subtitle_auto=False,
                       subtitle_embed=False, subtitle_languages=())
    return replace(request, subtitle_auto=auto, subtitle_languages=languages)


def media_options(request):
    mode = MediaMode(request.media_mode)
    if mode is MediaMode.AUDIO_ONLY:
        result = {'format': request.format.format_selector}
        if request.audio_codec != 'original':
            processor = {'key': 'FFmpegExtractAudio', 'preferredcodec': request.audio_codec}
            if request.audio_quality != 'original':
                processor['preferredquality'] = request.audio_quality
            result['postprocessors'] = [processor]
        return result
    if mode is MediaMode.VIDEO_ONLY:
        if not request.format.audio_format_id and request.format.acodec != 'none':
            raise ValueError('该格式包含声音，请选择独立视频流。')
        return {'format': request.format.video_format_id}
    if request.use_native_format:
        # Let this installed yt-dlp choose and merge its own video/audio pair.
        # A displayed quality option is not a verified native format selector.
        return {}
    return {'format': request.format.format_selector, 'merge_output_format': request.format.final_ext}

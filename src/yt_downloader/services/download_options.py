"""Translate a structured media request into yt-dlp stream selection."""
from dataclasses import replace
from yt_downloader.core.models import MediaMode
from yt_downloader.services.video_sections import validate_clip


def prepare_request(request):
    """Derive the actual output and progress contract before any IO."""
    request = _effective_subtitle_request(request)
    mode = MediaMode(request.media_mode)
    validate_clip(request.clip_enabled, request.clip_start, request.clip_end, request.video.duration)
    if request.clip_enabled and (request.video.is_collection or request.playlist_item_index is not None):
        raise ValueError('Clip downloads are only available for a single video.')
    if request.sponsorblock_mark and not str(request.video.extractor_key or '').casefold().startswith('youtube'):
        raise ValueError('SponsorBlock marking is only available for supported YouTube videos.')
    remux_container = str(request.remux_container or '').lower()
    if remux_container:
        if mode is MediaMode.AUDIO_ONLY:
            raise ValueError('Remux is only available for video output.')
        from yt_dlp.postprocessor.ffmpeg import FFmpegVideoRemuxerPP
        if remux_container not in FFmpegVideoRemuxerPP.SUPPORTED_EXTS:
            raise ValueError('Unsupported remux container.')
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
    playlist_selector = ({'playlist_items': str(request.playlist_item_index)}
                         if request.playlist_item_index is not None else {})
    if mode is MediaMode.AUDIO_ONLY:
        result = {'format': request.format.format_selector, **playlist_selector}
        if request.audio_codec != 'original':
            processor = {'key': 'FFmpegExtractAudio', 'preferredcodec': request.audio_codec}
            if request.audio_quality != 'original':
                processor['preferredquality'] = request.audio_quality
            result['postprocessors'] = [processor]
    elif mode is MediaMode.VIDEO_ONLY:
        if not request.format.audio_format_id and request.format.acodec != 'none':
            raise ValueError('该格式包含声音，请选择独立视频流。')
        result = {'format': request.format.video_format_id, **playlist_selector}
    elif request.use_native_format:
        # Let this installed yt-dlp choose and merge its own video/audio pair.
        # A displayed quality option is not a verified native format selector.
        result = dict(playlist_selector)
    else:
        result = {'format': request.format.format_selector, 'merge_output_format': request.format.final_ext,
                  **playlist_selector}
    if request.clip_enabled:
        from yt_dlp.utils import download_range_func
        result['download_ranges'] = download_range_func(None, [(request.clip_start, request.clip_end)])
        result['force_keyframes_at_cuts'] = False
        if request.clip_start > 0 and request.format.acodec.split('.')[0].lower() == 'opus':
            # Separate Opus inputs can seek to an earlier packet and retain
            # negative timestamps in stream-copy mode. Matroska then shifts the
            # entire mux timeline, adding preroll and delaying video. Discard
            # that preroll within the native FFmpegFD output, without encoding
            # or changing yt-dlp's input seek, URLs, mapping or format choice.
            result['external_downloader_args'] = {'ffmpeg_o': ['-ss', '0']}
    if request.embed_thumbnail:
        result['embedthumbnail'] = True
    if request.embed_metadata:
        result['addmetadata'] = True
    # Explicit false prevents yt-dlp from implicitly enabling chapters when
    # metadata or SponsorBlock marking is enabled. Leave yt-dlp's default alone
    # for ordinary downloads that did not request any post-processing.
    if request.embed_metadata or request.embed_chapters or request.sponsorblock_mark:
        result['addchapters'] = bool(request.embed_chapters or request.sponsorblock_mark)
    if request.remux_container:
        result['remuxvideo'] = str(request.remux_container).lower()
    if request.sponsorblock_mark:
        result['sponsorblock_mark'] = {'sponsor'}
    return result

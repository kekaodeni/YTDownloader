"""Semantic download defaults used to initialize new parsed tasks."""

from __future__ import annotations

import re

from yt_downloader.core.models import DownloadProfile


BUILTIN_PROFILES = (
    DownloadProfile('auto', '自动推荐'),
    DownloadProfile('best', '最高质量', quality_tier='highest'),
)
BUILTIN_PROFILE_IDS = frozenset(profile.id for profile in BUILTIN_PROFILES)
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
_QUALITIES = {'recommended', 'highest', '2160p', '1440p', '1080p', '720p'}
_CONTENT_MODES = {'video_audio', 'video_only', 'audio_only'}
_CODECS = {'auto', 'av1', 'vp9', 'h264'}
_AUDIO_CODECS = {'original', 'm4a', 'mp3', 'opus', 'flac'}
_AUDIO_QUALITIES = {'original', '320', '256', '192', '128'}


def profile_from_mapping(value: object) -> DownloadProfile:
    if not isinstance(value, dict):
        raise ValueError('下载预设数据无效。')
    languages = value.get('subtitle_languages', ())
    if not isinstance(languages, (tuple, list)) or any(not isinstance(item, str) for item in languages):
        raise ValueError('字幕语言设置无效。')
    # Only semantic, explicitly supported values may enter persistence.
    profile = DownloadProfile(
        id=str(value.get('id', '')),
        name=str(value.get('name', '')).strip(),
        content_mode=str(value.get('content_mode', 'video_audio')),
        quality_tier=str(value.get('quality_tier', 'recommended')),
        codec_preference=str(value.get('codec_preference', 'auto')),
        audio_codec=str(value.get('audio_codec', 'original')),
        audio_quality=str(value.get('audio_quality', 'original')),
        subtitle_enabled=bool(value.get('subtitle_enabled', False)),
        subtitle_auto=bool(value.get('subtitle_auto', False)),
        subtitle_embed=bool(value.get('subtitle_embed', False)),
        subtitle_format=str(value.get('subtitle_format', 'srt')),
        subtitle_languages=tuple(languages),
    )
    validate_profile(profile)
    return profile


def validate_profile(profile: DownloadProfile) -> None:
    if not _ID.fullmatch(profile.id) or profile.id in BUILTIN_PROFILE_IDS:
        raise ValueError('下载预设标识无效。')
    if not profile.name or len(profile.name) > 48:
        raise ValueError('预设名称需为 1–48 个字符。')
    if profile.content_mode not in _CONTENT_MODES:
        raise ValueError('下载内容设置无效。')
    if profile.quality_tier not in _QUALITIES:
        raise ValueError('画质设置无效。')
    if profile.codec_preference not in _CODECS:
        raise ValueError('视频编码设置无效。')
    if profile.audio_codec not in _AUDIO_CODECS or profile.audio_quality not in _AUDIO_QUALITIES:
        raise ValueError('音频设置无效。')
    if profile.subtitle_format not in {'srt', 'vtt'}:
        raise ValueError('字幕格式设置无效。')
    if any(type(value) is not bool for value in (profile.subtitle_enabled, profile.subtitle_auto, profile.subtitle_embed)):
        raise ValueError('字幕开关设置无效。')
    if len(profile.subtitle_languages) > 32 or any(not code or len(code) > 32 for code in profile.subtitle_languages):
        raise ValueError('字幕语言设置无效。')


def builtins() -> tuple[DownloadProfile, ...]:
    return BUILTIN_PROFILES


def profiles_by_id(custom_profiles: tuple[DownloadProfile, ...]) -> dict[str, DownloadProfile]:
    return {profile.id: profile for profile in (*BUILTIN_PROFILES, *custom_profiles)}

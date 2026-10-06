"""Immutable domain models shared by services and Qt workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import hashlib
from typing import Any, Mapping


SUPPORTED_LOCALES = (
    'zh-CN', 'zh-TW', 'en-US', 'ja-JP', 'ko-KR',
    'ru-RU', 'es-ES', 'pt-BR', 'vi-VN', 'th-TH',
)


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    FETCHING_METADATA = "FETCHING_METADATA"
    READY = "READY"
    DOWNLOADING_VIDEO = "DOWNLOADING_VIDEO"
    DOWNLOADING_AUDIO = "DOWNLOADING_AUDIO"
    MERGING = "MERGING"
    POST_PROCESSING = "POST_PROCESSING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ParseState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    SLOW = "SLOW"
    CANCELLING = "CANCELLING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class AuthState(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TotalSource(StrEnum):
    UNKNOWN = "UNKNOWN"
    METADATA_FILESIZE = "METADATA_FILESIZE"
    HOOK_TOTAL_BYTES = "HOOK_TOTAL_BYTES"
    METADATA_FILESIZE_APPROX = "METADATA_FILESIZE_APPROX"
    HOOK_TOTAL_BYTES_ESTIMATE = "HOOK_TOTAL_BYTES_ESTIMATE"
    FINAL_FILE = "FINAL_FILE"
    MIXED = "MIXED"
    # Compatibility aliases for callers that only need the broad source.
    METADATA = "METADATA_FILESIZE"
    HOOK = "HOOK_TOTAL_BYTES"
    FINAL = "FINAL_FILE"


ProgressTotalSource = TotalSource


class CodecPreference(StrEnum):
    AUTO = "auto"
    AV1 = "av1"
    VP9 = "vp9"
    H264 = "h264"


class MediaMode(StrEnum):
    VIDEO_AUDIO = "video_audio"
    VIDEO_ONLY = "video_only"
    AUDIO_ONLY = "audio_only"


class CollectionQualityMode(StrEnum):
    RESOLVED_COMMON_FORMATS = "RESOLVED_COMMON_FORMATS"
    DEFERRED_BATCH_TARGET = "DEFERRED_BATCH_TARGET"
    REFERENCE_EPISODE_FORMATS = "REFERENCE_EPISODE_FORMATS"


class SizeKind(StrEnum):
    EXACT = "EXACT"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


STATUS_TEXT: Mapping[TaskStatus, str] = {
    TaskStatus.PENDING: "等待下载",
    TaskStatus.FETCHING_METADATA: "正在获取视频信息",
    TaskStatus.READY: "准备就绪",
    TaskStatus.DOWNLOADING_VIDEO: "正在下载视频",
    TaskStatus.DOWNLOADING_AUDIO: "正在下载音频",
    TaskStatus.MERGING: "正在合并视频与音频",
    TaskStatus.POST_PROCESSING: "正在处理文件",
    TaskStatus.PAUSING: "正在暂停…",
    TaskStatus.PAUSED: "已暂停",
    TaskStatus.RESUMING: "正在继续…",
    TaskStatus.CANCELLING: "正在取消…",
    TaskStatus.COMPLETED: "下载完成",
    TaskStatus.FAILED: "下载失败",
    TaskStatus.CANCELLED: "已取消",
}

TASK_STATUS_MESSAGE_IDS: Mapping[TaskStatus, str] = {
    status: f'task.status.{status.value.lower()}' for status in TaskStatus
}


@dataclass(frozen=True, slots=True)
class CodecFormatVariant:
    codec_preference: CodecPreference
    video_format_id: str
    audio_format_id: str | None
    format_selector: str
    vcodec: str
    acodec: str
    container: str
    final_ext: str
    estimated_size: int | None
    requires_merge: bool
    width: int | None
    height: int | None
    fps: float | None
    video_size: int | None
    video_size_is_estimate: bool
    audio_size: int | None
    audio_size_is_estimate: bool
    video_protocol: str
    audio_protocol: str
    video_extension: str
    audio_extension: str
    size_kind: SizeKind
    dynamic_range: str = ""


@dataclass(frozen=True, slots=True)
class FormatOption:
    label: str
    height: int | None
    fps: float | None
    vcodec: str
    acodec: str
    container: str
    final_ext: str
    format_selector: str
    estimated_size: int | None
    requires_merge: bool
    video_format_id: str
    audio_format_id: str | None = None
    is_recommended: bool = False
    size_is_estimate: bool = False
    width: int | None = None
    video_size: int | None = None
    video_size_is_estimate: bool = False
    audio_size: int | None = None
    audio_size_is_estimate: bool = False
    video_protocol: str = ""
    audio_protocol: str = ""
    size_kind: SizeKind = SizeKind.UNKNOWN
    video_extension: str = ''
    audio_extension: str = ''
    candidate_video_format_ids: tuple[str, ...] = ()
    codec_variants: tuple[CodecFormatVariant, ...] = ()
    site_quality: int | None = None
    semantic_height: int | None = None
    semantic_fps: float | None = None
    quality_rank: int | None = None
    semantic_portrait: bool | None = None
    dynamic_range: str = ""
    detected_width: int | None = None
    detected_height: int | None = None
    detected_fps: float | None = None
    display_metadata_source: str = "yt-dlp"

    @property
    def display_height(self) -> int | None:
        if self.semantic_height is not None:
            return self.semantic_height
        width = self.width if self.width is not None else self.detected_width
        height = self.height if self.height is not None else self.detected_height
        if height is None:
            return None
        if width is not None and height > width:
            return width
        return height

    @property
    def display_fps(self) -> float | None:
        if self.quality_rank is not None:
            return self.semantic_fps
        return self.fps if self.fps is not None else self.detected_fps

    @property
    def quality_sort_key(self) -> tuple[int, int, float, int]:
        """Rank a choice by its user-facing tier while retaining raw media fields."""
        return (
            self.display_height or 0,
            self.quality_rank or 0,
            self.display_fps or 0,
            self.estimated_size or 0,
        )

    @property
    def technical_summary(self) -> str:
        if self.vcodec == 'none':
            return f'{self.container} · {self.acodec.upper()} · 仅音频'
        codec = self.vcodec.split(".", 1)[0].upper()
        audio = self.acodec.split(".", 1)[0].upper() if self.acodec != "none" else "无音频"
        merge = " · 需要自动合并" if self.requires_merge else ""
        return f"{self.container} · {codec} · {audio}{merge}"


@dataclass(frozen=True, slots=True)
class ResolvedMedia:
    video_id: str
    url: str
    title: str
    channel: str
    duration: float | None
    thumbnail_url: str | None
    thumbnail_bytes: bytes | None
    formats: tuple[FormatOption, ...]
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    extractor: str = ''
    extractor_key: str = ''
    original_url: str = ''
    webpage_url: str = ''
    media_type: str = 'video'
    uploader: str = ''
    upload_date: str | None = None
    description: str = ''
    subtitles: tuple[SubtitleTrack, ...] = ()
    automatic_captions: tuple[SubtitleTrack, ...] = ()
    playlist: PlaylistMetadata | None = None
    compatibility: str = 'EXPERIMENTAL'
    metadata_compatibility: str = 'EXPERIMENTAL'
    download_compatibility: str = 'EXPERIMENTAL'
    audio_formats: tuple[FormatOption, ...] = ()
    video_only_formats: tuple[FormatOption, ...] = ()
    entries: tuple[PlaylistEntry, ...] = ()
    entries_truncated: bool = False
    auth_state: AuthState = AuthState.NOT_APPLICABLE
    collection: Collection | None = None
    collection_quality_formats: tuple[FormatOption, ...] = ()
    collection_quality_mode: CollectionQualityMode | str = ''
    cookie_used: bool = False
    chapters: tuple[MediaChapter, ...] = ()
    thumbnails: tuple[ThumbnailOption, ...] = ()
    # Collection row identity survives a child's independent native extraction.
    canonical_thumbnail_url: str = ''
    collection_thumbnail_url: str = ''

    @property
    def is_collection(self) -> bool:
        """Whether yt-dlp resolved this result as a selectable collection."""
        return self.collection is not None or self.media_type in {'playlist', 'multi_video'}

    @property
    def collection_kind(self) -> str:
        """Retain the extractor distinction while presenting one UI concept."""
        return self.collection.kind if self.collection is not None else self.media_type if self.is_collection else ''

    @property
    def media_key(self) -> str:
        """Cross-extractor identity safe for matching and local file names."""
        identity = '\0'.join((self.extractor, self.webpage_url or self.url, self.video_id))
        return hashlib.sha256(identity.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class ThumbnailOption:
    url: str
    width: int | None = None
    height: int | None = None
    preference: float = 0


@dataclass(frozen=True, slots=True)
class MediaChapter:
    start_time: float
    end_time: float | None
    title: str


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    language: str
    extension: str
    url: str
    name: str = ''
    is_auto: bool = False
    data: str = ''

    @property
    def language_code(self):
        return self.language

    @property
    def display_name(self):
        from yt_downloader.services.subtitle_service import language_name
        return language_name(self.language)

    @property
    def source_type(self):
        return 'automatic' if self.is_auto else 'manual'

    @property
    def formats(self):
        return (self.extension,)


@dataclass(frozen=True, slots=True)
class PlaylistMetadata:
    id: str = ''
    title: str = ''
    index: int | None = None
    count: int | None = None


@dataclass(frozen=True, slots=True)
class PlaylistEntry:
    id: str
    index: int
    title: str
    url: str
    extractor_key: str = ''
    duration: float | None = None
    thumbnail: str = ''
    unavailable: bool = False
    formats: tuple[FormatOption, ...] = ()
    audio_formats: tuple[FormatOption, ...] = ()
    video_only_formats: tuple[FormatOption, ...] = ()
    embedded: bool = False
    selected_format: FormatOption | None = None
    quality_target: str = 'recommended'
    chapters: tuple[MediaChapter, ...] = ()
    availability: str = ''
    title_missing: bool = False

    @property
    def entry_kind(self) -> str:
        return 'embedded' if self.embedded else 'external'

    @property
    def available(self) -> bool:
        return not self.unavailable


@dataclass(frozen=True, slots=True)
class Collection:
    """Unified UI-facing collection while retaining yt-dlp entry kinds."""

    kind: str
    entries: tuple[PlaylistEntry, ...]
    truncated: bool = False

    @property
    def entry_count(self) -> int:
        return len(self.entries)


# Keep existing download/history consumers and older fixtures source-compatible.
# video_id is an extractor-local opaque ID, never a YouTube-specific identifier.
VideoInfo = ResolvedMedia
MediaInfo = ResolvedMedia


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    task_id: str
    video: VideoInfo
    format: FormatOption
    output_directory: Path
    filename_stem: str
    media_mode: MediaMode = MediaMode.VIDEO_AUDIO
    audio_codec: str = 'original'
    audio_quality: str = 'original'
    subtitle_enabled: bool = False
    subtitle_languages: tuple[str, ...] = ()
    subtitle_auto: bool = False
    subtitle_embed: bool = False
    subtitle_format: str = 'srt'
    cookie_profile: CookieProfile | None = None
    cookie_profile_id: str = ''
    batch_id: str = ''
    playlist_id: str = ''
    playlist_title: str = ''
    resolve_before_download: bool = False
    preferred_quality: str = 'recommended'
    codec_preference: CodecPreference = CodecPreference.AUTO
    use_native_format: bool = False
    resume_partial: bool = False
    playlist_item_index: int | None = None
    clip_enabled: bool = False
    clip_start: int = 0
    clip_end: int = 0
    embed_thumbnail: bool = False
    embed_metadata: bool = False
    embed_chapters: bool = False
    remux_container: str = ''
    sponsorblock_mark: bool = False
    metadata_language: str = ''


@dataclass(frozen=True, slots=True)
class CookieProfile:
    id: str
    name: str
    source_type: str
    browser: str = ''
    cookie_file: str = field(default='', repr=False)
    domain_hint: str = ''
    created_at: str = ''
    updated_at: str = ''
    browser_profile: str = ''


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    task_id: str
    status: TaskStatus
    percent: float | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: int | None = None
    total_is_estimate: bool = False
    total_source: TotalSource = TotalSource.UNKNOWN
    resolved_quality: str = ''
    resolved_thumbnail_url: str = ''
    resolved_thumbnail_bytes: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class DownloadResult:
    task_id: str
    file_path: Path
    file_size: int
    completed_at: str
    warnings: tuple[str, ...] = ()
    subtitle_paths: tuple[Path, ...] = ()
    subtitle_embedded: bool = False
    subtitle_auto_used: bool = False
    resolved_media: ResolvedMedia | None = field(default=None, repr=False)
    resolved_format: FormatOption | None = None


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    task_id: str
    video_id: str
    url: str
    title: str
    file_path: Path
    quality_label: str
    file_size: int | None
    thumbnail_path: Path | None
    status: TaskStatus
    created_at: str
    completed_at: str | None = None
    error_summary: str | None = None
    media_mode: str = 'video_audio'
    audio_codec: str = 'original'
    audio_bitrate: str = 'original'
    container: str = ''
    subtitle_languages: tuple[str, ...] = ()
    subtitle_format: str = 'srt'
    subtitle_embedded: bool = False
    subtitle_auto_used: bool = False

    extractor: str = ''
    source_site: str = ''
    playlist_id: str = ''
    playlist_title: str = ''
    batch_id: str = ''


@dataclass(frozen=True, slots=True)
class DownloadProfile:
    """A named set of semantic defaults; never stores resolver format IDs."""

    id: str
    name: str
    content_mode: str = 'video_audio'
    quality_tier: str = 'recommended'
    codec_preference: str = 'auto'
    audio_codec: str = 'original'
    audio_quality: str = 'original'
    subtitle_enabled: bool = False
    subtitle_auto: bool = False
    subtitle_embed: bool = False
    subtitle_format: str = 'srt'
    subtitle_languages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AppSettings:
    schema_version: int = 7
    download_directory: str = ""
    theme: str = "system"
    reduce_motion: bool = False
    ffmpeg_directory: str = ""
    proxy_mode: str = "system"
    custom_proxy_url: str = ""
    concurrent_fragments: int = 0
    max_concurrent_downloads: int = 2
    auto_check_updates: bool = True
    use_cookies: bool = False
    default_download_profile_id: str = 'auto'
    custom_download_profiles: tuple[DownloadProfile, ...] = ()
    language: str = 'zh-CN'
    prevent_duplicate_downloads: bool = True
    system_notifications: bool = True

    @property
    def default_profile(self) -> DownloadProfile:
        for profile in self.custom_download_profiles:
            if profile.id == self.default_download_profile_id:
                return profile
        if self.default_download_profile_id == 'best':
            return DownloadProfile('best', '最高质量', quality_tier='highest')
        return DownloadProfile('auto', '自动推荐')

    # Compatibility projections keep existing resolver and retry call sites
    # on the one profile source of truth while those paths are migrated.
    @property
    def default_quality(self) -> str:
        return self.default_profile.quality_tier

    @property
    def codec_preference(self) -> CodecPreference:
        return CodecPreference(self.default_profile.codec_preference)

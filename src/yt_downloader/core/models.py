"""Immutable domain models shared by services and Qt workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import hashlib
from typing import Any, Mapping


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    FETCHING_METADATA = "FETCHING_METADATA"
    READY = "READY"
    DOWNLOADING_VIDEO = "DOWNLOADING_VIDEO"
    DOWNLOADING_AUDIO = "DOWNLOADING_AUDIO"
    MERGING = "MERGING"
    POST_PROCESSING = "POST_PROCESSING"
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
    TaskStatus.CANCELLING: "正在取消…",
    TaskStatus.COMPLETED: "下载完成",
    TaskStatus.FAILED: "下载失败",
    TaskStatus.CANCELLED: "已取消",
}


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

    @property
    def display_height(self) -> int | None:
        if self.height is None:
            return None
        if self.width is not None and self.height > self.width:
            return self.width
        return self.height

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

    @property
    def media_key(self) -> str:
        """Cross-extractor identity safe for matching and local file names."""
        identity = '\0'.join((self.extractor, self.webpage_url or self.url, self.video_id))
        return hashlib.sha256(identity.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    language: str
    extension: str
    url: str
    name: str = ''
    is_auto: bool = False

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
    use_native_format: bool = False


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
class AppSettings:
    schema_version: int = 5
    download_directory: str = ""
    default_quality: str = "recommended"
    theme: str = "system"
    reduce_motion: bool = False
    ffmpeg_directory: str = ""
    proxy_mode: str = "system"
    custom_proxy_url: str = ""
    concurrent_fragments: int = 0
    max_concurrent_downloads: int = 2
    codec_preference: CodecPreference = CodecPreference.AUTO
    auto_check_updates: bool = True
    use_cookies: bool = False


@dataclass(frozen=True, slots=True)
class BatchTask:
    batch_id: str
    source_url: str
    title: str
    total_count: int
    selected_count: int
    created_at: str
    queued_count: int = 0
    active_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    status: str = 'queued'

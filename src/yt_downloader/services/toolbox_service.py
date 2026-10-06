"""Standalone media assets using the application's existing media services."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from yt_downloader.core.errors import AppError, ErrorContext, OperationCancelled
from yt_downloader.core.filename import sanitize_filename, ensure_unique_path
from yt_downloader.core.models import ResolvedMedia, CookieProfile
from yt_downloader.services.subtitle_service import SubtitleService


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    video: ResolvedMedia
    output_directory: Path
    thumbnail_url: str = ''
    subtitle_languages: tuple[str, ...] = ()
    subtitle_auto: bool = False
    subtitle_format: str = 'srt'
    cookie_profile: CookieProfile | None = None
    subtitle_enabled: bool = True
    subtitle_embed: bool = False


@dataclass(frozen=True)
class ToolResult:
    files: tuple[Path, ...]
    warning_count: int = 0


class ToolboxService:
    def __init__(self, resolver, subtitle_service=None):
        self.resolver = resolver
        self.subtitles = subtitle_service or SubtitleService(network_policy=resolver.network_policy)

    def execute(self, request, cancel_event):
        if cancel_event.is_set():
            raise OperationCancelled()
        directory = request.output_directory
        if not directory.is_absolute():
            raise AppError('invalid_output', '请选择有效的绝对下载目录。', 'Invalid Toolbox output directory')
        directory.mkdir(parents=True, exist_ok=True)
        if request.tool == 'thumbnail':
            return self._thumbnail(request, cancel_event)
        if request.tool != 'subtitles' or request.subtitle_format not in {'srt', 'vtt', 'ass'}:
            raise ValueError('Unsupported Toolbox request')
        temporary = directory / '.ytdownloader-tmp'
        temporary.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix='subtitles-', dir=temporary) as folder:
            result = self.subtitles.download_tracks(request, Path(folder), cancel_event)
            if not result.files:
                if result.error:
                    raise result.error
                raise AppError('subtitle_download_failed', '', 'No requested subtitles were saved',
                               ErrorContext(url=request.video.url, stage='Downloading subtitles'),
                               body_message_id='toolbox.subtitles_failed', recommended_actions=('RETRY', 'OPEN_COOKIE_MANAGER'))
            files = []
            for language, source in result.files:
                if cancel_event.is_set():
                    raise OperationCancelled()
                extension = f'.{language}.{request.subtitle_format}'
                name = sanitize_filename(request.video.title, directory=directory, extension=extension)
                target = ensure_unique_path(directory / (name + extension))
                with target.open('xb') as output:
                    output.write(source.read_bytes())
                files.append(target)
            return ToolResult(tuple(files), len(result.warnings))

    def _thumbnail(self, request, cancel_event):
        valid = {item.url for item in request.video.thumbnails}
        if request.video.thumbnail_url:
            valid.add(request.video.thumbnail_url)
        if not request.thumbnail_url or request.thumbnail_url not in valid:
            raise ValueError('Thumbnail is not an extractor-provided candidate')
        data = self.resolver.fetch_thumbnail(request.thumbnail_url, cancel_event)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError('Thumbnail exceeds size limit')
        with Image.open(BytesIO(data)) as image:
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif', 'AVIF': 'avif'}.get(image.format)
            image.verify()
        if not extension:
            raise ValueError('Unsupported thumbnail image format')
        if cancel_event.is_set():
            raise OperationCancelled()
        directory = request.output_directory
        name = sanitize_filename(request.video.title, directory=directory, extension='.' + extension)
        target = ensure_unique_path(directory / f'{name}.{extension}')
        with target.open('xb') as output:
            output.write(data)
        return ToolResult((target,))

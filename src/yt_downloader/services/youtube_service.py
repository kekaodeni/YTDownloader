"""Compatibility import; new callers use the generic MediaResolver."""
from yt_downloader.services.media_resolver import MediaResolver

YoutubeService = MediaResolver

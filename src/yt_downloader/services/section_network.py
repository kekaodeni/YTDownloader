"""Propagate yt-dlp's resolved proxy policy to its native FFmpeg inputs."""
import os
from urllib.parse import urlsplit

from yt_dlp.utils.networking import select_proxy
from yt_downloader.core.errors import AppError


def section_process_options(args, env, proxies):
    # FFmpeg does not read Windows Internet Settings. Do not let inherited
    # variables override the direct/custom/system policy resolved by yt-dlp.
    child_env = dict(os.environ if env is None else env)
    for key in tuple(child_env):
        if key.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}:
            del child_env[key]
    result = []
    for index, value in enumerate(args):
        if value == '-i' and index + 1 < len(args) and urlsplit(args[index + 1]).scheme in {'http', 'https'}:
            proxy = select_proxy(args[index + 1], proxies)
            if proxy == '__noproxy__':
                proxy = None
            if proxy and urlsplit(proxy).scheme not in {'http', 'https', ''}:
                # FFmpeg cannot consume yt-dlp's SOCKS proxy transport. Never
                # guess an HTTP alternative or silently download directly.
                raise AppError('NETWORK_ERROR', '网络连接失败，请检查网络或代理后重试。',
                               'FFmpeg section inputs require an HTTP CONNECT proxy; the selected proxy transport is unsupported.')
            result.extend(['-http_proxy', proxy or ''])
        result.append(value)
    return result, child_env

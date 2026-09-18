"""Conservative metadata error categories; ambiguous failures stay unclassified."""
import re
import requests
from yt_dlp.utils import GeoRestrictedError, UnsupportedError


def classify_metadata_error(error):
    pending, chain, seen = [error], [], set()
    while pending:
        item = pending.pop()
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        chain.append(item)
        pending.extend([getattr(item, '__cause__', None), getattr(item, 'cause', None)])
        info = getattr(item, 'exc_info', None)
        if isinstance(info, tuple) and len(info) > 1:
            pending.append(info[1])
    message = ' '.join(str(item) for item in chain).lower()
    if any(isinstance(item, UnsupportedError) for item in chain) or 'unsupported url' in message:
        return 'UNSUPPORTED_URL', 'yt-dlp 暂不支持该链接，请检查地址或尝试单个视频页面。'
    if any(isinstance(item, GeoRestrictedError) for item in chain) or any(text in message for text in ('not available in your country', 'geo-restricted', 'not available in your region')):
        return 'GEO_RESTRICTED', '该媒体在当前地区不可用。'
    if any(text in message for text in ('drm protected', 'drm-protected', 'has drm', 'drm protection')):
        return 'DRM_UNSUPPORTED', '该媒体受 DRM 保护，无法处理。'
    if any(text in message for text in ('private video', 'video is private', 'private media', 'this video is private')):
        return 'PRIVATE_MEDIA', '该媒体为私有内容，当前无法访问。'
    if re.search(r'(?:use|provide|requires?|pass|supply|need)\b[^.\n]{0,80}\bcookies?\b|--cookies(?:-from-browser)?', message):
        return 'COOKIE_REQUIRED', '网站要求有效 Cookie；当前版本尚不提供 Cookie 导入。'
    if any(text in message for text in ('login required', 'log in to', 'sign in to', 'authentication required', 'requires authentication', 'age-restricted', 'confirm your age')):
        return 'AUTH_REQUIRED', '该媒体需要登录或年龄验证；当前版本尚不提供登录功能。'
    if any(isinstance(item, (requests.RequestException, ConnectionError, TimeoutError)) for item in chain) or any(text in message for text in ('timed out', 'connection refused', 'connection reset', 'name resolution', 'getaddrinfo failed', 'network is unreachable', 'unable to connect', 'certificate verify failed')):
        return 'NETWORK_ERROR', '网络连接失败，请检查网络或代理后重试。'
    return 'TEMPORARY_EXTRACTOR_ERROR', '解析器暂时无法获取媒体信息，请重试或更新 yt-dlp。'

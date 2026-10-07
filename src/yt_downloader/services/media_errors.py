"""Conservative metadata error categories; ambiguous failures stay unclassified."""
import re
from collections.abc import Mapping
import requests
from yt_dlp.utils import GeoRestrictedError, UnsupportedError
from yt_downloader.core.models import AuthState


# Exact native X API rejection messages, scoped to a matched X Cookie source.
# A generic HTTP 401 or a request to log in does not prove session invalidity.
X_AUTH_INVALID_PATTERNS = (
    r'\bcould not authenticate you\b',
    r'\bauthentication failed\b',
    r'\binvalid or expired token\b',
)

# Messages checked against the bundled native extractors. Broad "no formats"
# or "no video found" errors do not prove that the content has no media.
NO_MEDIA_PATTERNS = {
    'twitter': (r'no video could be found in this tweet',),
    'bluesky': (r'no video could be found in this post',),
    'tumblr': (r'no video could be found in this post',),
    'instagram': (r'there is no video in this post',),
    'reddit': (r'no media found',),
    'floatplane': (r'post does not contain a video or audio track',),
}
RESTRICTED_AVAILABILITY = frozenset({'private', 'premium_only', 'subscriber_only', 'needs_auth', 'unavailable'})


def classify_no_media_evidence(*, exception=None, provider='', extractor_key='', metadata=None,
                              auth_state=AuthState.NOT_APPLICABLE):
    """Require explicit native evidence, never just an empty formats array.

    The private metadata marker is produced only by the collection adapter
    after an independently classified native child exception.
    """
    if AuthState(auth_state) is AuthState.INVALID:
        return None
    if isinstance(metadata, Mapping):
        if metadata.get('availability') in RESTRICTED_AVAILABILITY or metadata.get('has_drm'):
            return None
        if metadata.get('_app_no_downloadable_media') is True and not metadata.get('formats'):
            return 'NO_DOWNLOADABLE_MEDIA'
        entries = metadata.get('entries')
        if (metadata.get('_type') in {'playlist', 'multi_video'} and isinstance(entries, list)
                and (metadata.get('id') or metadata.get('title'))):
            if not entries or all(isinstance(entry, Mapping) and
                    classify_no_media_evidence(metadata=entry) for entry in entries):
                return 'NO_DOWNLOADABLE_MEDIA'
    if exception is None:
        return None
    # Keep auth, content restrictions and transport failures ahead of an empty
    # result, also when this helper is used independently of the classifier.
    if classify_metadata_error(exception, _allow_no_media=False)[0] != 'TEMPORARY_EXTRACTOR_ERROR':
        return None
    chain = _exception_chain(exception)
    text = ' '.join(str(item) for item in chain).lower()
    if re.search(r'\bhttp(?: error)?\s*:?\s*[45]\d\d\b', text):
        return None
    keys = {str(provider).casefold(), str(extractor_key).casefold()}
    keys.update(str(getattr(item, 'ie', '') or '').casefold() for item in chain)
    keys.update(re.findall(r'\[([a-z]+)\]', text))
    if keys & {'x', 'x.com', 'twitter.com'} or 'in this tweet' in text:
        keys.add('twitter')
    if any(re.search(pattern, text) for pattern in X_AUTH_INVALID_PATTERNS):
        return None
    for key in keys:
        for pattern in NO_MEDIA_PATTERNS.get(key, ()):
            if re.search(r'\b' + pattern + r'\b', text):
                return 'NO_DOWNLOADABLE_MEDIA'
    return None


def _exception_chain(error):
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
    return chain


def classify_auth_metadata_error(error, *, auth_state, cookie_matched=False, site=''):
    """Refine an extraction failure using independently observed auth evidence."""
    text = ' '.join(str(item) for item in _exception_chain(error)).lower()
    if cookie_matched and site == 'X' and any(re.search(pattern, text) for pattern in X_AUTH_INVALID_PATTERNS):
        return 'COOKIE_INVALID', f'{site} 的 Cookie 已失效，请重新登录浏览器或更新 Cookie 配置后再试。', AuthState.INVALID
    code, message = classify_metadata_error(error)
    stale = bool(re.search(r'fresh\s+cookies?[^.\n]{0,100}(?:needed|required)|'
                          r'cookies? (?:have |has |are |is )?(?:expired|no longer valid)|'
                          r'session (?:has |is )?(?:expired|invalid)', text))
    no_video = 'no video could be found in this tweet' in text
    if cookie_matched and (stale or auth_state is AuthState.INVALID and
                           (code in {'COOKIE_REQUIRED', 'AUTH_REQUIRED', 'NO_DOWNLOADABLE_MEDIA'} or site == 'X' and no_video)):
        return 'COOKIE_INVALID', f'{site} 的 Cookie 已失效，请重新登录浏览器或更新 Cookie 配置后再试。', AuthState.INVALID
    if code == 'NO_DOWNLOADABLE_MEDIA' and auth_state is AuthState.INVALID:
        return 'TEMPORARY_EXTRACTOR_ERROR', '解析器暂时无法获取媒体信息，请重试或更新 yt-dlp。', auth_state
    return code, message, auth_state


def classify_metadata_error(error, *, _allow_no_media=True):
    chain = _exception_chain(error)
    message = ' '.join(str(item) for item in chain).lower()
    if 'could not copy chrome cookie database' in message or ('cookie' in message and 'database is locked' in message):
        return 'BROWSER_PROFILE_LOCKED', '浏览器 Cookie 数据库可能被占用或无权读取，请关闭浏览器后重试。'
    if 'failed to decrypt' in message or 'could not be decrypted' in message:
        return 'COOKIE_DECRYPT_FAILED', '无法解密浏览器 Cookie，请使用当前 Windows 用户的浏览器，或选择 cookies.txt。'
    if ('cookie' in message and ('could not find' in message or 'failed to load' in message)):
        return 'BROWSER_COOKIE_READ_FAILED', '无法读取所选浏览器的 Cookie，请检查浏览器配置或选择 Cookie 文件。'
    if any(isinstance(item, GeoRestrictedError) for item in chain) or any(text in message for text in ('not available in your country', 'geo-restricted', 'not available in your region')):
        return 'GEO_RESTRICTED', '该媒体在当前地区不可用。'
    if any(text in message for text in ('drm protected', 'drm-protected', 'has drm', 'drm protection')):
        return 'DRM_UNSUPPORTED', '该媒体受 DRM 保护，无法处理。'
    if any(text in message for text in ('private video', 'video is private', 'private media', 'this video is private')):
        return 'PRIVATE_MEDIA', '该媒体为私有内容，当前无法访问。'
    if (re.search(r'(?:use|provide|requires?|pass|supply|need)\b[^.\n]{0,80}\bcookies?\b|--cookies(?:-from-browser)?', message)
            or re.search(r'fresh\s+cookies?[^.\n]{0,100}\b(?:are\s+)?(?:needed|required)\b', message)):
        return 'COOKIE_REQUIRED', '此内容需要登录状态，请选择 Cookie 配置后重新解析。'
    if any(text in message for text in ('login required', 'log in to', 'sign in to', 'authentication required', 'requires authentication', 'age-restricted', 'confirm your age')):
        return 'AUTH_REQUIRED', '该媒体需要登录或年龄验证，请使用你有权访问内容的 Cookie 配置。'
    if any(isinstance(item, (requests.RequestException, ConnectionError, TimeoutError)) for item in chain) or any(text in message for text in ('timed out', 'connection refused', 'connection reset', 'name resolution', 'getaddrinfo failed', 'network is unreachable', 'unable to connect', 'certificate verify failed')):
        return 'NETWORK_ERROR', '网络连接失败，请检查网络或代理后重试。'
    if re.search(r'(?:video|post|content) (?:has been |was |is )?(?:removed|deleted)', message):
        return 'CONTENT_UNAVAILABLE', '该内容已删除或不再可用。'
    if 'requested format is not available' in message:
        return 'FORMAT_UNAVAILABLE', '所选画质已不可用，请重新解析视频。'
    if _allow_no_media and classify_no_media_evidence(exception=error):
        return 'NO_DOWNLOADABLE_MEDIA', '这个链接中没有检测到可下载的视频或音频。'
    if any(isinstance(item, UnsupportedError) for item in chain) or 'unsupported url' in message:
        return 'UNSUPPORTED_URL', 'yt-dlp 暂不支持该链接，请检查地址或尝试单个视频页面。'
    return 'TEMPORARY_EXTRACTOR_ERROR', '解析器暂时无法获取媒体信息，请重试或更新 yt-dlp。'


def classify_download_error(message: str) -> tuple[str, str]:
    lowered = message.lower()
    if (re.search(r'\d+ bytes read,\s*\d+ more expected', lowered)
            or any(text in lowered for text in ('incompleteread', 'connection reset',
                                               'remote end closed connection', 'premature eof'))):
        return 'DOWNLOAD_INTERRUPTED', '下载连接中断，请重试。'
    if re.search(r"\b(?:http(?:/\d(?:\.\d)?)?(?:\s+error)?|server returned)\s*:?\s*429\b", lowered) or 'too many requests' in lowered:
        return 'rate_limited', '请求过于频繁，请稍后再试。'
    if re.search(r"\b(?:http(?:/\d(?:\.\d)?)?(?:\s+error)?|server returned)\s*:?\s*403\b", lowered) or 'forbidden' in lowered:
        return 'forbidden', '网站拒绝了下载请求，可能与登录权限、访问限制或临时站点策略有关。请稍后重试。'
    if 'ffmpeg' in lowered and re.search(r'connection (?:to|attempt)[^\n]*failed|unable to connect|connection timed out', lowered):
        return 'FFMPEG_NETWORK_ERROR', 'FFmpeg 无法连接视频媒体服务器。片段下载需要 FFmpeg 直接访问媒体地址，请检查网络或代理后重试。'
    category, user_message = classify_metadata_error(Exception(message))
    if category == 'FORMAT_UNAVAILABLE':
        return 'format_unavailable', user_message
    if category != 'TEMPORARY_EXTRACTOR_ERROR':
        return category, user_message
    if "no space" in lowered or "disk full" in lowered:
        return "disk_full", "磁盘空间不足，无法完成下载。"
    if "ffmpeg" in lowered:
        return "ffmpeg_failed", "FFmpeg 处理视频失败。"
    if "requested format" in lowered:
        return "format_unavailable", "所选画质已不可用，请重新解析视频。"
    return "download_failed", "下载未能完成。"

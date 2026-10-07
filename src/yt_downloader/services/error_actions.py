"""Stable user actions for existing semantic error categories."""

from __future__ import annotations


ERROR_PRESENTATION = {
    'NO_DOWNLOADABLE_MEDIA': ('media.no_downloadable.title', 'media.no_downloadable.body', ()),
    'CONTENT_UNAVAILABLE': ('media.unavailable.title', 'media.unavailable.body', ()),
    'COOKIE_INVALID': ('error.cookie_invalid.title', 'error.cookie_invalid.body',
                       ('OPEN_COOKIE_MANAGER', 'REPARSE')),
    'NO_VIDEO': ('error.no_video.title', 'error.no_video.body', ()),
    'forbidden': ('error.forbidden.title', 'error.forbidden.body', ()),
    'COOKIE_REQUIRED': ('error.cookie_required.title', 'error.cookie_required.body',
                        ('OPEN_COOKIE_MANAGER', 'REPARSE')),
    'AUTH_REQUIRED': ('error.auth_required.title', 'error.auth_required.body',
                      ('OPEN_COOKIE_MANAGER', 'REPARSE')),
    'COOKIE_DECRYPT_FAILED': ('error.auth_required.title', 'error.auth_required.body',
                              ('OPEN_COOKIE_MANAGER', 'REPARSE')),
    'BROWSER_COOKIE_READ_FAILED': ('error.auth_required.title', 'error.auth_required.body',
                                   ('OPEN_COOKIE_MANAGER', 'REPARSE')),
    'BROWSER_PROFILE_LOCKED': ('error.browser_locked.title', 'error.browser_locked.body',
                               ('RETRY', 'OPEN_COOKIE_MANAGER')),
    'format_unavailable': ('error.format_stale.title', 'error.format_stale.body', ('REPARSE',)),
    'FORMAT_UNAVAILABLE': ('error.format_stale.title', 'error.format_stale.body', ('REPARSE',)),
    'NETWORK_ERROR': ('error.network.title', 'error.network.body', ('RETRY',)),
    'DOWNLOAD_INTERRUPTED': ('error.network.title', 'error.interrupted.body', ('RETRY',)),
    'FFMPEG_NETWORK_ERROR': ('error.network.title', 'error.ffmpeg_network.body', ('RETRY',)),
    'TEMPORARY_EXTRACTOR_ERROR': ('error.extractor.title', 'error.extractor.body',
                                  ('RETRY', 'CHECK_APP_UPDATE')),
}


def error_presentation(code: str, *, retry_available: bool = False):
    """Return message IDs and a bounded action set without inspecting raw stderr."""
    title, body, actions = ERROR_PRESENTATION.get(str(code), ('', '', ()))
    if retry_available and not actions and str(code) not in {'NO_DOWNLOADABLE_MEDIA', 'CONTENT_UNAVAILABLE'}:
        return '', '', ('RETRY',)
    return title, body, actions

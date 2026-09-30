import pytest

from yt_downloader.services.download_service import _download_error


@pytest.mark.parametrize('message,code', [
    ('This format is DRM protected; Try selecting another format', 'DRM_UNSUPPORTED'),
    ('This video is private', 'PRIVATE_MEDIA'),
    ('Not available in your country', 'GEO_RESTRICTED'),
    ('Connection timed out', 'NETWORK_ERROR'),
    ('Unsupported URL: https://example.org/media', 'UNSUPPORTED_URL'),
    ('Unclassified remote failure', 'download_failed'),
])
def test_download_retains_specific_extractor_failure_category(message, code):
    assert _download_error(message)[0] == code


def test_ffmpeg_exit_code_is_not_an_http_rate_limit():
    assert _download_error('ERROR: ffmpeg exited with code 4294967158')[0] == 'ffmpeg_failed'
    assert _download_error('ERROR: ffmpeg exited with code -138')[0] == 'ffmpeg_failed'


@pytest.mark.parametrize('message,code', [
    ('HTTP Error 429: Too Many Requests', 'rate_limited'),
    ('Server returned 429 Too Many Requests', 'rate_limited'),
    ('HTTP Error 403: Forbidden', 'forbidden'),
    ('Server returned 403 Forbidden', 'forbidden'),
    ('FFmpeg: HTTP/1.1 429\nConnection to tcp://media:443 failed', 'rate_limited'),
])
def test_http_errors_keep_their_actual_status(message, code):
    assert _download_error(message)[0] == code


def test_ffmpeg_tcp_failure_uses_transport_evidence_not_numeric_exit_code():
    message = ('ERROR: ffmpeg exited with code 4294967158\n'
               'FFmpeg: Connection to tcp://media.example:443 failed: Error number -138 occurred')
    assert _download_error(message)[0] == 'FFMPEG_NETWORK_ERROR'

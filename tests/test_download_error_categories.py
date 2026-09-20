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

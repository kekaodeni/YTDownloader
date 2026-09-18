from dataclasses import replace
import pytest
from yt_dlp.utils import DownloadError, GeoRestrictedError

from yt_downloader.core.errors import AppError
from yt_downloader.core.url import InvalidMediaUrl, normalize_media_url
from yt_downloader.services.error_report_service import build_error_report, redact_sensitive
from test_generic_media import media_fixture, service_for


@pytest.mark.parametrize('url', ['https://vimeo.com/123', 'http://media.example/file.mp4?q=1#part', 'https://www.bilibili.com/video/BV1xx411c7mD', 'https://youtube.com/playlist?list=PL123', 'https://[::1]:8080/video'])
def test_url_entry_accepts_http_without_site_allowlist(url):
    assert normalize_media_url(url) == url


@pytest.mark.parametrize('url', ['', 'file:///video.mp4', 'javascript:alert(1)', 'ftp://site/video', 'https:///no-host', 'https://user:password@host/video', 'https://host:99999/video', 'https://host:/video', 'https://host/line\nnext', 'https://host\\evil/video'])
def test_input_rejects_unsafe_urls(url):
    with pytest.raises(InvalidMediaUrl):
        normalize_media_url(url)


@pytest.mark.parametrize('message,code', [
    ('Unsupported URL: https://unsupported.example', 'UNSUPPORTED_URL'),
    ('Unable to download webpage: Connection timed out', 'NETWORK_ERROR'),
    ('Login required to watch this video', 'AUTH_REQUIRED'),
    ('Use --cookies-from-browser to authenticate', 'COOKIE_REQUIRED'),
    ('This video is not available in your country', 'GEO_RESTRICTED'),
    ('This video is private', 'PRIVATE_MEDIA'),
    ('This video is DRM protected', 'DRM_UNSUPPORTED'),
    ('HTTP Error 403: Forbidden', 'TEMPORARY_EXTRACTOR_ERROR'),
    ('Unable to extract title', 'TEMPORARY_EXTRACTOR_ERROR'),
    ('The title mentions geography, cookies and age', 'TEMPORARY_EXTRACTOR_ERROR'),
])
def test_errors_use_explicit_evidence_and_keep_copyable_details(message, code):
    with pytest.raises(AppError) as caught:
        service_for(None, error=DownloadError(message)).fetch_metadata('https://media.example/video')
    assert caught.value.code == code
    assert message in build_error_report(caught.value, app_version='test')


def test_typed_geo_error_wins_over_ambiguous_text():
    cause = GeoRestrictedError('Not available')
    with pytest.raises(AppError) as caught:
        service_for(None, error=DownloadError('Not available', exc_info=(type(cause), cause, None))).fetch_metadata('https://media.example/video')
    assert caught.value.code == 'GEO_RESTRICTED'


def test_playlist_saves_summary_without_consuming_entries_or_enabling_download(quick_window):
    class NoIteration:
        def __iter__(self):
            raise AssertionError('Playlist enumeration is outside Phase 2')
    seen = []
    result = service_for({'_type': 'playlist', 'id': 'collection', 'title': 'Collection',
                          'extractor': 'vimeo', 'entries': NoIteration()}, seen).fetch_metadata('https://vimeo.com/showcase/123')
    assert result.media_type == 'playlist' and result.playlist.id == 'collection'
    assert result.formats == () and result.raw == {}
    assert seen[0][1]['noplaylist'] is True and seen[0][1]['extract_flat'] == 'in_playlist'
    quick_window.download_page.show_video(result)
    assert '后续版本' in quick_window.download_page.state['mediaHint']


def test_missing_metadata_is_safe_and_thumbnail_fallback_works():
    data = media_fixture('vimeo', 'https://vimeo.com/123')
    data.update(id=None, title=None, uploader=None, channel=None, duration=float('nan'), thumbnail=None,
                subtitles=None, automatic_captions={'en': None}, thumbnails=[{'url': 'file:///private'}, {'url': 'https://cdn.example/thumb.jpg'}])
    result = service_for(data).fetch_metadata('https://vimeo.com/123', include_thumbnail=False)
    assert result.title == '未命名媒体' and result.duration is None
    assert result.thumbnail_url == 'https://cdn.example/thumb.jpg'
    assert result.subtitles == () and result.automatic_captions == ()
    assert result.media_key != replace(result, webpage_url='https://vimeo.com/456').media_key


def test_generic_reports_redact_url_credentials_and_signed_query():
    result = redact_sensitive('https://user:supersecret@host/path?signature=secret-signature&token=private-token')
    assert 'supersecret' not in result and 'secret-signature' not in result and 'private-token' not in result


def test_generic_record_coexists_with_legacy_history(tmp_path):
    import sqlite3
    from test_history_repository import _record
    from yt_downloader.core.models import TaskStatus
    from yt_downloader.services.history_service import HistoryRepository
    repository = HistoryRepository(tmp_path/'history.db')
    original = _record(tmp_path, 'legacy', TaskStatus.COMPLETED)
    repository.upsert(original)
    media = service_for(media_fixture('BiliBili', 'https://www.bilibili.com/video/BV1xx411c7mD')).fetch_metadata('https://www.bilibili.com/video/BV1xx411c7mD', include_thumbnail=False)
    repository.upsert(replace(original, task_id='generic', video_id=media.media_key, url=media.webpage_url, title=media.title))
    with sqlite3.connect(tmp_path/'history.db') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert db.execute('SELECT video_id,url FROM downloads WHERE task_id=?', ('legacy',)).fetchone() == (original.video_id, original.url)
        assert db.execute('SELECT video_id,url FROM downloads WHERE task_id=?', ('generic',)).fetchone() == (media.media_key, media.webpage_url)

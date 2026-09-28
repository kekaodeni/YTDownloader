import json

import pytest

from yt_downloader.core.models import AppSettings, DownloadProfile
from yt_downloader.services.download_profiles import BUILTIN_PROFILES
from yt_downloader.services.settings_service import SettingsService


def test_builtin_profiles_are_only_auto_and_best():
    assert [(profile.id, profile.name, profile.quality_tier) for profile in BUILTIN_PROFILES] == [
        ('auto', '自动推荐', 'recommended'),
        ('best', '最高质量', 'highest'),
    ]


def test_legacy_default_quality_and_codec_migrate_to_semantic_profile(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({
        'schema_version': 5,
        'download_directory': str(tmp_path),
        'default_quality': '1080p',
        'codec_preference': 'h264',
        'theme': 'dark',
    }), encoding='utf-8')
    service = SettingsService(path, default_download_directory=tmp_path)

    settings = service.load()

    assert settings.default_download_profile_id not in {'auto', 'best'}
    migrated = next(profile for profile in settings.custom_download_profiles
                    if profile.id == settings.default_download_profile_id)
    assert migrated.quality_tier == '1080p'
    assert migrated.codec_preference == 'h264'
    assert settings.theme == 'dark'

    service.save(settings)
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['schema_version'] == 6
    assert saved['custom_download_profiles'][0]['quality_tier'] == '1080p'
    assert 'default_quality' not in saved
    assert 'codec_preference' not in saved
    assert json.loads((tmp_path / 'settings.v5.backup.json').read_text(encoding='utf-8'))['schema_version'] == 5


def test_v1_development_keys_are_ignored_without_corrupting_global_settings(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({
        'schema_version': 5,
        'download_directory': str(tmp_path),
        'theme': 'light',
        'custom_profiles': [{'id': 'v1-profile', 'name': 'V1'}],
        'default_profile_id': 'v1-profile',
        'profiles': [{'id': 'bad-schema'}],
    }), encoding='utf-8')
    settings = SettingsService(path, default_download_directory=tmp_path).load()

    assert settings.theme == 'light'
    assert settings.default_download_profile_id == 'auto'
    assert settings.custom_download_profiles == ()


def test_custom_profile_storage_contains_only_semantic_download_options(tmp_path):
    path = tmp_path / 'settings.json'
    profile = DownloadProfile('p-anime', '动漫收藏', quality_tier='1080p',
                              codec_preference='vp9', subtitle_enabled=True,
                              subtitle_auto=True, subtitle_languages=('zh-Hans',))
    service = SettingsService(path, default_download_directory=tmp_path)
    service.save(AppSettings(download_directory=str(tmp_path),
                             default_download_profile_id=profile.id,
                             custom_download_profiles=(profile,)))

    payload = json.loads(path.read_text(encoding='utf-8'))
    stored = payload['custom_download_profiles'][0]
    assert payload['default_download_profile_id'] == profile.id
    assert stored == {
        'id': 'p-anime', 'name': '动漫收藏', 'content_mode': 'video_audio',
        'quality_tier': '1080p', 'codec_preference': 'vp9', 'audio_codec': 'original',
        'audio_quality': 'original', 'subtitle_enabled': True, 'subtitle_auto': True,
        'subtitle_embed': False, 'subtitle_format': 'srt', 'subtitle_languages': ['zh-Hans'],
    }
    assert not {'format_id', 'format_selector', 'cookie', 'cookie_profile', 'proxy'} & stored.keys()


def test_invalid_semantic_profile_is_rejected_before_settings_are_overwritten(tmp_path):
    path = tmp_path / 'settings.json'
    service = SettingsService(path, default_download_directory=tmp_path)
    service.save(AppSettings(download_directory=str(tmp_path)))
    previous = path.read_text(encoding='utf-8')

    with pytest.raises(ValueError, match='视频编码'):
        service.save(AppSettings(download_directory=str(tmp_path),
                                 default_download_profile_id='p-invalid',
                                 custom_download_profiles=(DownloadProfile(
                                     'p-invalid', 'Invalid', codec_preference='bestvideo'),)))

    assert path.read_text(encoding='utf-8') == previous

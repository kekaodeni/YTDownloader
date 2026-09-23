import json
from pathlib import Path

import pytest

from yt_downloader.core.models import AppSettings, CodecPreference
from yt_downloader.services.settings_service import SettingsService


def test_round_trips_settings_atomically(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path, default_download_directory=tmp_path / "视频")
    defaults = service.load()
    assert defaults.download_directory.endswith("视频")
    assert defaults.theme == "system"

    changed = AppSettings(
        download_directory=str(tmp_path / "下载😀"),
        default_quality="1080",
        theme="dark",
        reduce_motion=True,
        ffmpeg_directory="C:/工具/ffmpeg",
    )
    service.save(changed)
    assert service.load() == changed
    assert not path.with_suffix(".json.tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 5


def test_schema_four_cookie_preference_migrates_to_boolean_with_backup(tmp_path: Path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'schema_version': 4, 'download_directory': str(tmp_path),
                                'default_cookie_profile_id': 'old-id'}), encoding='utf-8')
    service = SettingsService(path, default_download_directory=tmp_path)
    settings = service.load()
    assert settings.schema_version == 5
    assert settings.use_cookies is True
    service.save(settings)
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['use_cookies'] is True
    assert 'default_cookie_profile_id' not in saved
    assert json.loads((tmp_path / 'settings.v4.backup.json').read_text(encoding='utf-8'))['default_cookie_profile_id'] == 'old-id'


def test_recovers_from_invalid_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"theme":"neon"}', encoding="utf-8")
    service = SettingsService(path, default_download_directory=tmp_path)
    assert service.load().theme == "system"


def test_migrates_schema_one_with_a_copy_first_backup(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "download_directory": "D:/旧目录",
                "default_quality": "1080p",
                "theme": "dark",
                "reduce_motion": True,
                "ffmpeg_directory": "D:/tools",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = SettingsService(path, default_download_directory=tmp_path)

    migrated = service.load()

    assert migrated.schema_version == 5
    assert migrated.download_directory == "D:/旧目录"
    assert not (tmp_path / "settings.v1.backup.json").exists()

    service.save(migrated)

    backup = tmp_path / "settings.v1.backup.json"
    assert json.loads(backup.read_text(encoding="utf-8"))["schema_version"] == 1
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 5


def test_rejects_invalid_custom_proxy_without_overwriting_saved_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path, default_download_directory=tmp_path)
    saved = AppSettings(download_directory=str(tmp_path), proxy_mode="direct")
    service.save(saved)

    with pytest.raises(ValueError, match="自定义代理"):
        service.save(AppSettings(
            download_directory=str(tmp_path),
            proxy_mode="custom",
            custom_proxy_url="not-a-proxy",
        ))

    assert service.load() == saved


def test_invalid_custom_proxy_in_existing_file_recovers_to_safe_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "schema_version": 2,
        "download_directory": str(tmp_path),
        "proxy_mode": "custom",
        "custom_proxy_url": "broken-value",
    }), encoding="utf-8")

    loaded = SettingsService(path, default_download_directory=tmp_path).load()

    assert loaded.proxy_mode == "system"
    assert loaded.custom_proxy_url == ""


def test_migrates_schema_two_to_codec_policy_with_copy_first_backup(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "schema_version": 2,
        "download_directory": str(tmp_path / "视频"),
        "default_quality": "recommended",
        "theme": "dark",
        "proxy_mode": "system",
        "concurrent_fragments": 4,
    }, ensure_ascii=False), encoding="utf-8")
    service = SettingsService(path, default_download_directory=tmp_path)

    migrated = service.load()

    assert migrated.schema_version == 5
    assert migrated.codec_preference is CodecPreference.AUTO
    service.save(migrated)
    assert json.loads((tmp_path / "settings.v2.backup.json").read_text(encoding="utf-8"))["schema_version"] == 2
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 5


def test_migrates_schema_three_to_auto_update_setting_with_copy_first_backup(tmp_path: Path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({
        'schema_version': 3,
        'download_directory': str(tmp_path / '视频'),
        'theme': 'dark', 'proxy_mode': 'direct', 'codec_preference': 'vp9',
        'auto_check_updates': False,
    }, ensure_ascii=False), encoding='utf-8')
    service = SettingsService(path, default_download_directory=tmp_path)
    migrated = service.load()
    assert migrated.schema_version == 5
    assert migrated.auto_check_updates is False
    service.save(migrated)
    assert json.loads((tmp_path / 'settings.v3.backup.json').read_text(encoding='utf-8'))['schema_version'] == 3
    assert json.loads(path.read_text(encoding='utf-8'))['schema_version'] == 5

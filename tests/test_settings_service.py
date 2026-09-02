import json
from pathlib import Path

from yt_downloader.core.models import AppSettings
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
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_recovers_from_invalid_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"theme":"neon"}', encoding="utf-8")
    service = SettingsService(path, default_download_directory=tmp_path)
    assert service.load().theme == "system"

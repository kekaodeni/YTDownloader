"""Locally compiled updater capabilities and fixed bundle layouts."""
from pathlib import Path
from semver import Version
from yt_downloader.updates.models import UpdateManifest

LEGACY_LAYOUT = 'legacy-root'
INTERNAL_LAYOUT = 'internal-v1'
HELPER_PATHS = {LEGACY_LAYOUT: Path('YTDownloaderUpdater.exe'),
                INTERNAL_LAYOUT: Path('_internal/updater/YTDownloaderUpdater.exe')}


def supported_protocols(version: str) -> tuple[int, ...]:
    return (2,) if Version.parse(version) >= Version.parse('0.5.0') else (1, 2)


def compatible(manifest: UpdateManifest, current_version: str, updater_version: str) -> bool:
    current = Version.parse(current_version)
    return (
        manifest.version > current and not manifest.version.prerelease
        and current >= manifest.minimum_auto_update_version
        and Version.parse(updater_version) >= manifest.minimum_updater_version
        and manifest.updater_protocol in supported_protocols(updater_version)
        and (manifest.schema_version, manifest.updater_protocol, manifest.helper_layout)
        in {(1, 1, LEGACY_LAYOUT), (2, 2, INTERNAL_LAYOUT)}
        and (current < Version.parse('0.5.0') or manifest.schema_version == 2)
    )

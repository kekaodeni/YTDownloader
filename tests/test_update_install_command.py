from pathlib import Path

from yt_downloader.updates.models import UpdateCapability
from yt_downloader.updates.models import UpdateManifest, UpdatePackage, VerifiedUpdatePackage
from semver import Version
from yt_downloader.updates.service import UpdateService
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.state import UpdateStateStore


def test_prepare_install_is_denied_outside_auto_install_capability(tmp_path):
    service = UpdateService(
        current_version='0.4.0', discovery=None, fetch_bytes=lambda _url: b'',
        keyring=TrustedKeyring({}), state_store=UpdateStateStore(tmp_path/'state.json'),
        downloader=None, staging_root=tmp_path/'staging',
        capability=UpdateCapability.DOWNLOAD_AND_VERIFY,
    )
    assert service.prepare_install_command(tmp_path, tmp_path, 1) is None


def test_auto_install_command_copies_owned_updater_outside_install_tree(tmp_path):
    install = tmp_path / 'install'; install.mkdir()
    updater = install / 'YTDownloaderUpdater.exe'; updater.write_bytes(b'updater')
    staging = tmp_path / 'staging'; transaction = staging / 'update-tx'; transaction.mkdir(parents=True)
    package_path = transaction / 'YTDownloader-0.4.1-win64.zip'; package_path.write_bytes(b'zip')
    manifest = UpdateManifest(
        Version.parse('0.4.1'), 'now', Version.parse('0.4.0'), 1, 'key', 'zh', 'en', 'release',
        UpdatePackage(package_path.name, 'url', 3, 4, '0' * 64),
    )
    service = UpdateService(
        current_version='0.4.0', discovery=None, fetch_bytes=lambda _url: b'',
        keyring=TrustedKeyring({}), state_store=UpdateStateStore(tmp_path/'state.json'),
        downloader=None, staging_root=staging, capability=UpdateCapability.AUTO_INSTALL,
    )
    service.verified_package = VerifiedUpdatePackage('tx', package_path, manifest)
    command = service.prepare_install_command(install, tmp_path/'data', 42)
    assert command is not None
    assert Path(command[0]).parent == transaction
    assert Path(command[0]).read_bytes() == b'updater'
    assert '--original-pid' in command and '42' in command

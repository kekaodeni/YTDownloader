"""Authenticated recovery handoff; the application never switches its own tree."""
from pathlib import Path
import hashlib
import shutil
import zipfile

from yt_downloader.updates.archive import SafePackageExtractor as Archive
from yt_downloader.updates.installation import InstallRequest, checked_path, validate_request
from yt_downloader.updates.protocol import HELPER_PATHS
from yt_downloader.updates.transaction import installation_mutex

TERMINAL = {'COMMITTED', 'ROLLED_BACK'}


def pending_recovery(install: Path, data: Path) -> InstallRequest | None:
    install, data = checked_path(install), checked_path(data)
    staging = checked_path(data/'update-staging')
    if not staging.exists():
        return None
    pending = []
    for transaction in sorted(staging.glob('update-*')):
        transaction = checked_path(transaction, exists=True)
        journal_path = checked_path(transaction/'update-transaction.json')
        if not journal_path.is_file():
            continue  # Download-only transactions use normal package revalidation.
        journal = Archive._load_json(journal_path)
        if not isinstance(journal, dict):
            raise ValueError('Invalid recovery journal')
        if checked_path(Path(journal.get('install_dir', ''))) != install:
            continue  # An independently installed copy owns this transaction.
        if journal.get('stage') in TERMINAL:
            continue
        binding = Archive._load_json(checked_path(transaction/'install-request.json', exists=True))
        request = InstallRequest(transaction, install, data, binding['current_version'],
                                 binding['target_version'], binding['original_pid'])
        request.validate_paths()
        pending.append(request)
    if len(pending) > 1:
        raise ValueError('Multiple unfinished transactions require independent inspection')
    return pending[0] if pending else None


def validate_journal(request, manifest):
    journal = Archive._load_json(checked_path(request.transaction/'update-transaction.json', exists=True))
    expected = dict(transaction_id=request.transaction.name, install_dir=str(request.install),
                    candidate_dir=str(request.install.parent/f'.{request.install.name}.candidate-{request.transaction.name}'),
                    backup_dir=str(request.install.parent/f'.{request.install.name}.backup-{request.transaction.name}'),
                    health_marker=str(request.transaction/'startup-health.json'))
    for field, value in expected.items():
        if field.endswith('_dir') or field == 'health_marker':
            actual = checked_path(Path(journal.get(field, '')))
            if actual != checked_path(Path(value)):
                raise ValueError('Recovery journal paths do not belong to this transaction')
        elif journal.get(field) != value:
            raise ValueError('Recovery journal identity changed')
    if journal.get('schema_version', 1) == 2:
        expected.update(source_version=request.current_version, target_version=request.target_version,
                        manifest_sha256=Archive.file_hash(request.transaction/'update-manifest.json'),
                        package_sha256=manifest.package.sha256)
        if any(journal.get(key) != value for key, value in expected.items()):
            raise ValueError('Recovery journal binding changed')
    return journal


def recovery_helper_hash(request, manifest, helper_version):
    if helper_version == request.current_version:
        binding = Archive._load_json(request.transaction/'install-request.json')
        return binding['helper_sha256']
    if helper_version != request.target_version:
        raise ValueError('Recovery helper version is unrelated to the transaction')
    # Trust comes from the verified signed package, never from an editable local
    # ownership file. This authorizes only the already installed target helper.
    with zipfile.ZipFile(request.transaction/manifest.package.name) as archive:
        members = Archive._validated_members(archive, manifest.package.extracted_size)
        name = HELPER_PATHS[manifest.helper_layout].as_posix()
        member = next((info for info, relative in members if relative.as_posix() == name), None)
        if member is None:
            raise ValueError('Signed package has no recovery helper')
        digest = hashlib.sha256()
        with archive.open(member) as source:
            while chunk := source.read(1024*1024):
                digest.update(chunk)
        return digest.hexdigest()


def validate_recovery(request, keyring, executing_helper, helper_version):
    manifest = validate_request(request, keyring,
                                executing_helper=request.transaction/'updater/YTDownloaderUpdater.exe', recovery=True)
    validate_journal(request, manifest)
    expected = request.transaction/'recovery-helper/YTDownloaderUpdater.exe'
    if checked_path(executing_helper, exists=True) != expected:
        raise ValueError('Recovery must run outside the installation in its owned staging')
    if Archive.file_hash(executing_helper) != recovery_helper_hash(request, manifest, helper_version):
        raise ValueError('Recovery helper does not match its trusted source')
    return manifest


def prepare_recovery(request, keyring, *, helper_version, parent_pid):
    if type(parent_pid) is not int or parent_pid <= 0:
        raise ValueError('Recovery parent pid must be positive')
    with installation_mutex(request.install):
        manifest = validate_request(request, keyring,
                                    executing_helper=request.transaction/'updater/YTDownloaderUpdater.exe', recovery=True)
        validate_journal(request, manifest)
        Archive.validate_tree(request.install, expected_version=helper_version)
        info = Archive._load_json(request.install/'BUILD-INFO.json')
        source = checked_path(request.install/HELPER_PATHS[Archive.layout(info)], exists=True)
        digest = recovery_helper_hash(request, manifest, helper_version)
        if Archive.file_hash(source) != digest:
            raise ValueError('Installed recovery helper changed')
        destination = checked_path(request.transaction/'recovery-helper/YTDownloaderUpdater.exe')
        destination.parent.mkdir(exist_ok=True)
        if destination.exists():
            if Archive.file_hash(destination) != digest:
                raise ValueError('Existing recovery helper changed; evidence preserved')
        else:
            with source.open('rb') as incoming, destination.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
        if Archive.file_hash(destination) != digest:
            raise ValueError('Staged recovery helper hash mismatch')
    return (str(destination), '--recover', '--recovery-parent-pid', str(parent_pid),
            '--transaction-dir', str(request.transaction), '--install-dir', str(request.install),
            '--data-dir', str(request.data), '--original-pid', str(request.original_pid),
            '--current-version', request.current_version, '--target-version', request.target_version)


def recovery_result(install, data, token):
    import re
    if not re.fullmatch(r'update-[A-Za-z0-9][A-Za-z0-9._-]{0,120}', token):
        raise ValueError('Invalid recovery result identity')
    transaction = checked_path(Path(data)/'update-staging'/token, exists=True)
    report = Archive._load_json(checked_path(transaction/'recovery-result.json', exists=True))
    journal = Archive._load_json(checked_path(transaction/'update-transaction.json', exists=True))
    if report.get('transaction_id') != token or checked_path(Path(journal['install_dir'])) != checked_path(install):
        raise ValueError('Recovery result belongs to another installation')
    if report.get('status') == 'ok' and journal.get('stage') not in TERMINAL:
        raise ValueError('Recovery has not reached a terminal state')
    return report

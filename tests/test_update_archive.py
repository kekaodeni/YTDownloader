import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest

from yt_downloader.updates.archive import SafePackageExtractor


def _write_package(path: Path, files: dict[str, bytes], *, extracted_size: int | None = None) -> int:
    sums = [
        {'Path': name, 'SHA256': hashlib.sha256(data).hexdigest()}
        for name, data in files.items()
    ]
    payloads = dict(files)
    payloads['SHA256SUMS.json'] = json.dumps(sums).encode()
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in payloads.items():
            archive.writestr(f'YTDownloader/{name}', data)
    return extracted_size if extracted_size is not None else sum(map(len, payloads.values()))


def test_safe_extractor_verifies_owned_file_manifest_and_critical_files(tmp_path):
    package = tmp_path / 'update.zip'
    size = _write_package(package, {
        'YTDownloader.exe': b'app',
        'YTDownloaderUpdater.exe': b'updater',
        'BUILD-INFO.json': json.dumps({'app_version': '0.4.1'}).encode(),
        '_internal/runtime.dll': b'dll',
    })
    candidate = tmp_path / 'candidate'
    result = SafePackageExtractor().extract(package, candidate, signed_extracted_size=size, expected_version='0.4.1')
    assert result == candidate
    assert (candidate / 'YTDownloader.exe').read_bytes() == b'app'


@pytest.mark.parametrize('entry', [
    '../outside.txt', '/absolute.txt', 'C:/drive.txt', 'safe/file.txt:stream',
    'CON.txt', 'nested/aux.log',
])
def test_safe_extractor_rejects_unsafe_names(tmp_path, entry):
    package = tmp_path / 'bad.zip'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr(f'YTDownloader/{entry}', b'bad')
    with pytest.raises(ValueError):
        SafePackageExtractor().extract(package, tmp_path / 'candidate', signed_extracted_size=3, expected_version='0.4.1')
    assert not (tmp_path / 'outside.txt').exists()


def test_safe_extractor_rejects_case_duplicates_and_symlinks(tmp_path):
    duplicate = tmp_path / 'duplicate.zip'
    with zipfile.ZipFile(duplicate, 'w') as archive:
        archive.writestr('YTDownloader/A.txt', b'a')
        archive.writestr('YTDownloader/a.TXT', b'b')
    with pytest.raises(ValueError, match='duplicate'):
        SafePackageExtractor().extract(duplicate, tmp_path / 'candidate-a', signed_extracted_size=2, expected_version='0.4.1')

    symlink = tmp_path / 'symlink.zip'
    info = zipfile.ZipInfo('YTDownloader/link')
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink, 'w') as archive:
        archive.writestr(info, '../target')
    with pytest.raises(ValueError, match='link'):
        SafePackageExtractor().extract(symlink, tmp_path / 'candidate-b', signed_extracted_size=9, expected_version='0.4.1')


def test_safe_extractor_rejects_size_bombs_and_unowned_files(tmp_path):
    package = tmp_path / 'size.zip'
    size = _write_package(package, {
        'YTDownloader.exe': b'app',
        'YTDownloaderUpdater.exe': b'updater',
        'BUILD-INFO.json': json.dumps({'app_version': '0.4.1'}).encode(),
    })
    with pytest.raises(ValueError, match='size'):
        SafePackageExtractor().extract(package, tmp_path / 'candidate', signed_extracted_size=size - 1, expected_version='0.4.1')

    unowned = tmp_path / 'unowned.zip'
    with zipfile.ZipFile(unowned, 'w') as archive:
        archive.writestr('YTDownloader/YTDownloader.exe', b'app')
        archive.writestr('YTDownloader/YTDownloaderUpdater.exe', b'updater')
        archive.writestr('YTDownloader/BUILD-INFO.json', json.dumps({'app_version': '0.4.1'}))
        archive.writestr('YTDownloader/SHA256SUMS.json', b'[]')
    total = sum(i.file_size for i in zipfile.ZipFile(unowned).infolist())
    with pytest.raises(ValueError, match='unowned'):
        SafePackageExtractor().extract(unowned, tmp_path / 'candidate-2', signed_extracted_size=total, expected_version='0.4.1')

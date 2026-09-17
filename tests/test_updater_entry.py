import ast
from pathlib import Path

import pytest

from yt_downloader_updater.__main__ import validate_upgrade_versions


def test_external_updater_entry_has_no_qt_dependency():
    source = Path('src/yt_downloader_updater/__main__.py').read_text(encoding='utf-8')
    imports = {
        node.names[0].name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
    } | {
        node.module or ''
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(name.startswith(('PySide', 'yt_downloader.app', 'yt_downloader.ui')) for name in imports)


def test_health_check_argument_is_registered_before_normal_gui_flow():
    source = Path('src/yt_downloader/app.py').read_text(encoding='utf-8')
    assert '--update-health-check' in source


def test_external_updater_refuses_replay_or_downgrade():
    assert tuple(map(str, validate_upgrade_versions('0.4.0', '0.4.1'))) == ('0.4.0', '0.4.1')
    with pytest.raises(ValueError, match='newer'):
        validate_upgrade_versions('0.4.0', '0.4.0')
    with pytest.raises(ValueError, match='newer'):
        validate_upgrade_versions('0.4.0', '0.3.0')


def test_manual_updater_without_transaction_arguments_exits_before_file_work():
    from yt_downloader_updater.__main__ import _arguments
    with pytest.raises(SystemExit):
        _arguments([])


def test_helper_with_missing_transaction_exits_without_mutating_install(tmp_path, monkeypatch):
    from yt_downloader_updater import __main__ as entry
    install = tmp_path / 'install'; install.mkdir()
    data = tmp_path / 'data'; data.mkdir()
    transaction = tmp_path / 'missing-transaction'
    monkeypatch.setattr(entry, 'PRODUCTION_TRUSTED_KEYS', {'test': b'x' * 32})
    with pytest.raises((ValueError, FileNotFoundError)):
        entry.run([
            '--transaction-dir', str(transaction), '--install-dir', str(install),
            '--data-dir', str(data), '--original-pid', '1',
            '--current-version', '0.4.2', '--target-version', '0.5.0',
        ])
    assert list(install.iterdir()) == []
    assert not transaction.exists()

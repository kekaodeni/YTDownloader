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

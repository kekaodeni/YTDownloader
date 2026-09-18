import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def verifier():
    spec = importlib.util.spec_from_file_location('quick_package_verifier', Path(__file__).resolve().parents[1] / 'scripts/verify_quick_package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_identity_rejects_wrong_version_or_source_before_launch(verifier, tmp_path):
    exe = tmp_path / 'YTDownloader.exe'
    exe.write_bytes(b'test-only')
    info = tmp_path / 'BUILD-INFO.json'
    info.write_text(json.dumps(dict(app_version='0.4.1', source_commit='a'*40)))
    with pytest.raises(ValueError, match='version'):
        verifier.verify_identity(exe, '0.4.2', 'a'*40)
    info.write_text(json.dumps(dict(app_version='0.4.2', source_commit='a'*40)))
    with pytest.raises(ValueError, match='source'):
        verifier.verify_identity(exe, '0.4.2', 'b'*40)
    assert verifier.verify_identity(exe, '0.4.2', 'a'*40)['app_version'] == '0.4.2'


def test_health_must_match_explicit_version_and_transaction(verifier):
    health = dict(status='ok', transaction_id='acceptance-unique', app_version='0.4.1')
    with pytest.raises(ValueError):
        verifier.verify_health(health, '0.4.2', 'acceptance-unique')
    health['app_version'] = '0.4.2'
    with pytest.raises(ValueError):
        verifier.verify_health(health, '0.4.2', 'another-transaction')
    verifier.verify_health(health, '0.4.2', 'acceptance-unique')

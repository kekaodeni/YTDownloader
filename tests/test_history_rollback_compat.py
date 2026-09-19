import subprocess
import sys
import types
from dataclasses import replace

from test_history_repository import _record
from yt_downloader.core.models import TaskStatus
from yt_downloader.services.history_service import HistoryRepository


def test_real_v042_repository_can_read_and_write_extended_history(tmp_path):
    source = subprocess.check_output(['git', 'show', 'v0.4.2:src/yt_downloader/services/history_service.py'], text=True, encoding='utf-8')
    module = types.ModuleType('legacy_v042_history_fixture')
    sys.modules[module.__name__] = module
    try:
        exec(compile(source, '<immutable v0.4.2 history>', 'exec'), module.__dict__)
        path = tmp_path / 'history.db'
        old = module.HistoryRepository(path)
        original = _record(tmp_path, 'old', TaskStatus.COMPLETED)
        old.upsert(original)
        modern = HistoryRepository(path)
        assert modern.get('old') == original
        modern.upsert(replace(original, task_id='new', media_mode='audio_only'))
        rolled_back = module.HistoryRepository(path)
        assert {r.task_id for r in rolled_back.list_records()} == {'old', 'new'}
        rolled_back.upsert(replace(original, task_id='after-rollback'))
        assert HistoryRepository(path).get('after-rollback') == replace(original, task_id='after-rollback')
    finally:
        sys.modules.pop(module.__name__, None)

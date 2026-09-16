"""Owned, serialized developer scratch sessions; never store them in the checkout."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import uuid


@contextmanager
def session(kind: str):
    if not kind or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in kind):
        raise ValueError('Invalid scratch kind')
    root = Path(tempfile.gettempdir()).resolve() / 'YTDownloader' / 'dev-staging' / kind
    checkout = Path(__file__).resolve().parents[1]
    if root.is_relative_to(checkout):
        raise ValueError('TEMP must be outside the checkout')
    root.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents parallel tasks from pruning one another.
    lock = root / '.active'
    with lock.open('x'):
        pass
    work = root / ('session-' + uuid.uuid4().hex)
    try:
        for previous in root.glob('session-*'):
            if previous.is_symlink():
                raise ValueError('Refusing linked scratch directory')
            shutil.rmtree(previous)
        work.mkdir()
        yield work
    except BaseException:
        print(f'Diagnostic scratch retained: {work}')
        raise
    else:
        shutil.rmtree(work)
    finally:
        lock.unlink()

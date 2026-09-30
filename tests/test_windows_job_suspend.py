import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from yt_downloader.infrastructure.windows_job import ProcessJob


@pytest.mark.skipif(os.name != 'nt', reason='Windows process suspension')
def test_job_suspends_and_resumes_the_same_parent_and_child(tmp_path):
    script = tmp_path / 'writer.py'
    script.write_text('''import pathlib, subprocess, sys, time
p = pathlib.Path(sys.argv[1])
if len(sys.argv) > 2:
    gate = pathlib.Path(sys.argv[2])
    while not gate.exists(): time.sleep(.01)
    subprocess.Popen([sys.executable, __file__, str(p.with_name('child.bin'))])
with p.open('ab', buffering=0) as f:
    while True:
        f.write(b'x' * 100)
        time.sleep(.02)
''', encoding='utf-8')
    parent_path, child_path = tmp_path / 'parent.bin', tmp_path / 'child.bin'
    gate = tmp_path / 'gate'
    job = ProcessJob()
    process = subprocess.Popen([sys.executable, str(script), str(parent_path), str(gate)])
    try:
        assert job.assign(process.pid)
        gate.touch()
        deadline = time.monotonic() + 3
        while not child_path.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert child_path.exists()
        assert process.pid in job.members()
        assert len(job.members()) >= 2  # venv Python may also own launcher processes
        job.suspend()
        sizes = [p.stat().st_size for p in (parent_path, child_path)]
        time.sleep(.3)
        assert [p.stat().st_size for p in (parent_path, child_path)] == sizes
        assert process.poll() is None
        job.resume()
        time.sleep(.3)
        assert all(p.stat().st_size > size for p, size in zip((parent_path, child_path), sizes))
        assert process.poll() is None
    finally:
        if not job.terminate():
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        process.wait(timeout=3)
        job.close()

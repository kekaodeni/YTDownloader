"""Minimal frozen metadata-helper self-test entry point without loading QML."""

from __future__ import annotations

import sys
import subprocess
import time


def run_helper_child() -> int:
    """Keep a frozen helper alive until the parent verifies termination."""
    while True:
        time.sleep(1)


def _run_frozen_helper_self_test() -> int:
    """Probe frozen helper startup without recursively spawning multiprocessing."""
    process = subprocess.Popen(
        [sys.executable, "--metadata-helper-self-test-child"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20.0
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is not None:
            return 2
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
        return 0 if process.returncode is not None else 2
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2.0)


def main() -> int:
    if getattr(sys, "frozen", False):
        return _run_frozen_helper_self_test()
    from PySide6.QtCore import QCoreApplication
    from yt_downloader.workers.metadata_process import run_metadata_process_self_test

    app = QCoreApplication([sys.argv[0], "--metadata-process-self-test"])
    return run_metadata_process_self_test(app)

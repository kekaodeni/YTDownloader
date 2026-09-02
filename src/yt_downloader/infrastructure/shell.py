"""Explicit user-triggered Windows Shell actions."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


def open_path(path: str | Path) -> None:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    os.startfile(str(target))  # type: ignore[attr-defined]


def reveal_in_folder(path: str | Path) -> None:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    subprocess.Popen(["explorer.exe", "/select,", str(target)], shell=False)


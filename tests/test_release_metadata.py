from __future__ import annotations

from pathlib import Path
import tomllib

from yt_downloader import __version__


def test_package_and_runtime_versions_match() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == "0.2.0"
    assert project["project"]["version"] == __version__

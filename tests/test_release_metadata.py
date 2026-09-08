from __future__ import annotations

from pathlib import Path
import tomllib

from yt_downloader import __version__


def test_package_and_runtime_versions_match() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == "0.4.0"
    assert project["project"]["version"] == __version__
    assert (project_root / "README.md").read_text(encoding="utf-8").startswith(
        "# YT Downloader 0.4.0"
    )
    build_script = (project_root / "scripts" / "build.ps1").read_text(encoding="utf-8")
    assert "--metadata-process-self-test" in build_script
    assert "YTDownloaderUpdater.spec" in build_script
    assert "Production update trust is not configured" in build_script
    assert 'SafePackageExtractor.validate_tree' in build_script
    assert '$RelativePath.Replace("\\", "/")' in build_script

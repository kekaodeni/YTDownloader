from __future__ import annotations

from pathlib import Path
import tomllib

from yt_downloader import __version__


def test_package_and_runtime_versions_match() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == "0.4.1"
    assert project["project"]["version"] == __version__
    assert (project_root / "README.md").read_text(encoding="utf-8").startswith(
        "# YT Downloader 0.4.1"
    )
    build_script = (project_root / "scripts" / "build.ps1").read_text(encoding="utf-8")
    assert "--metadata-process-self-test" in build_script
    assert "YTDownloaderUpdater.spec" in build_script
    assert "Production update trust is not configured" in build_script
    assert 'SafePackageExtractor.validate_tree' in build_script
    assert '$RelativePath.Replace("\\", "/")' in build_script


def test_packaged_self_test_runs_before_qml_initialization(monkeypatch, tmp_path: Path) -> None:
    import yt_downloader.app as app_module

    class _Paths:
        cache = tmp_path / "cache"
        logs = tmp_path / "logs"

        def ensure(self) -> None:
            self.cache.mkdir()
            self.logs.mkdir()

    monkeypatch.setattr(app_module.AppPaths, "discover", staticmethod(lambda: _Paths()))
    monkeypatch.setattr(app_module, "configure_logging", lambda _path: None)
    monkeypatch.setattr(app_module, "FfmpegService", lambda: object())
    monkeypatch.setattr(app_module, "find_tool", lambda _name: None)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(app_module, "run_packaged_self_test", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        app_module,
        "create_application",
        lambda _argv: (_ for _ in ()).throw(AssertionError("QML must not initialize for --self-test")),
    )

    assert app_module.main(["--self-test"]) == 0
    assert calls and calls[0]["cache_directory"] == tmp_path / "cache"

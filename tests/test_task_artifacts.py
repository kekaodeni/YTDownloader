from pathlib import Path

from yt_downloader.services.task_artifacts import TaskArtifactRegistry


def test_task_id_cannot_escape_the_owned_workspace(tmp_path: Path) -> None:
    output = tmp_path / "中文😀"
    output.mkdir()
    registry = TaskArtifactRegistry(output, "../../outside", sleeper=lambda _delay: None)

    registry.prepare()

    assert registry.workspace.parent == registry.temporary_root
    assert registry.workspace.resolve().is_relative_to(output.resolve())
    assert registry.cleanup().succeeded
    assert not registry.temporary_root.exists()


def test_cleanup_failure_is_bounded_and_returned_as_a_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "downloads"
    output.mkdir()
    registry = TaskArtifactRegistry(output, "task", sleeper=lambda _delay: None)
    registry.prepare()
    owned = registry.workspace / "download.mp4.part"
    owned.write_bytes(b"partial")
    unrelated = output / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")

    def fail_cleanup(_path):
        raise PermissionError("locked")

    monkeypatch.setattr(
        "yt_downloader.services.task_artifacts.shutil.rmtree",
        fail_cleanup,
    )

    report = registry.cleanup()

    assert not report.succeeded
    assert report.failed_paths == (str(registry.workspace),)
    assert report.errors == ("locked",)
    assert owned.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"

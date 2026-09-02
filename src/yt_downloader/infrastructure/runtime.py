"""Runtime resource and bundled-tool discovery for source and PyInstaller."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys


def bundle_root() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    return Path(frozen) if frozen else Path(__file__).resolve().parents[3]


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def find_tool(name: str, configured_directory: str | Path | None = None) -> Path | None:
    executable = f"{name}.exe" if sys.platform == "win32" else name
    candidates: list[Path] = []
    if configured_directory:
        configured = Path(configured_directory)
        candidates.append(configured if configured.name.lower() == executable.lower() else configured / executable)
    root = bundle_root()
    candidates.extend((
        root / "tools" / "ffmpeg" / executable,
        root / "tools" / "deno" / executable,
        root / "vendor" / "tools" / "ffmpeg" / executable,
        root / "vendor" / "tools" / "deno" / executable,
    ))
    discovered = shutil.which(executable)
    if discovered:
        candidates.append(Path(discovered))
    return next((path.resolve() for path in candidates if path.is_file()), None)


"""Collect pinned runtime package notices into a distributable directory."""

from __future__ import annotations

import argparse
from importlib import metadata
import json
from pathlib import Path
import re
import shutil


RUNTIME_DISTRIBUTIONS = (
    "PySide6",
    "PySide6-Addons",
    "PySide6-Essentials",
    "shiboken6",
    "yt-dlp",
    "yt-dlp-ejs",
    "requests",
    "PySocks",
    "Pillow",
    "brotli",
    "certifi",
    "charset-normalizer",
    "idna",
    "mutagen",
    "pycryptodomex",
    "urllib3",
    "websockets",
)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-_")


def _is_license_file(path: Path) -> bool:
    lowered_parts = {part.lower() for part in path.parts}
    lowered_name = path.name.lower()
    return "licenses" in lowered_parts or lowered_name.startswith(("license", "copying", "notice"))


def collect_runtime_licenses(destination: Path) -> list[dict[str, object]]:
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for requested_name in RUNTIME_DISTRIBUTIONS:
        distribution = metadata.distribution(requested_name)
        package_name = distribution.metadata.get("Name", requested_name)
        package_directory = destination / "python" / _safe_name(package_name)
        copied: list[str] = []
        for entry in distribution.files or ():
            relative = Path(str(entry))
            if not _is_license_file(relative):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file():
                continue
            target = package_directory / relative.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(destination).as_posix())
        records.append({
            "name": package_name,
            "version": distribution.version,
            "license_expression": distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "not declared in wheel metadata",
            "license_files": sorted(set(copied)),
        })
    manifest = destination / "PYTHON-RUNTIME-LICENSES.json"
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    collect_runtime_licenses(arguments.destination.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

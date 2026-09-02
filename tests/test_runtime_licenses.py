from __future__ import annotations

import json

from scripts.collect_runtime_licenses import RUNTIME_DISTRIBUTIONS, collect_runtime_licenses


def test_runtime_license_collection_writes_versions_and_available_texts(tmp_path) -> None:
    records = collect_runtime_licenses(tmp_path)
    by_name = {str(record["name"]).lower(): record for record in records}

    assert len(records) == len(RUNTIME_DISTRIBUTIONS)
    assert by_name["pyside6"]["version"]
    assert by_name["yt-dlp"]["license_files"]
    assert by_name["requests"]["license_files"]
    assert by_name["pysocks"]["version"] == "1.7.1"
    manifest = json.loads(
        (tmp_path / "PYTHON-RUNTIME-LICENSES.json").read_text(encoding="utf-8")
    )
    assert manifest == records
    for record in records:
        for relative_path in record["license_files"]:
            assert (tmp_path / str(relative_path)).is_file()

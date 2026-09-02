"""Windows-safe output naming that preserves meaningful Unicode."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata


_INVALID = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE)


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _trim_grapheme_tail(text: str) -> str:
    text = text[:-1]
    while text and unicodedata.combining(text[-1]):
        text = text[:-1]
    return text.rstrip(" .")


def sanitize_filename(
    value: str,
    *,
    directory: str | Path | None = None,
    extension: str = "",
    max_path_units: int = 240,
    max_name_units: int = 180,
) -> str:
    """Sanitize a filename stem for broad Windows path compatibility."""
    name = unicodedata.normalize("NFC", value).strip()
    name = _INVALID.sub("_", name).rstrip(" .")
    if not name:
        name = "YouTube 视频"
    if _RESERVED.fullmatch(name):
        name = f"_{name}"

    while name and _utf16_units(name) > max_name_units:
        name = _trim_grapheme_tail(name)

    if directory is not None:
        parent = Path(directory)
        while name and _utf16_units(str(parent / f"{name}{extension}")) > max_path_units:
            name = _trim_grapheme_tail(name)
        if not name:
            raise ValueError("下载目录路径过长，无法生成安全文件名。")
    return name


def ensure_unique_path(path: str | Path) -> Path:
    """Return a non-existing sibling path without overwriting user data."""
    candidate = Path(path)
    if not candidate.exists():
        return candidate
    for index in range(1, 10_000):
        alternative = candidate.with_name(f"{candidate.stem} ({index}){candidate.suffix}")
        if not alternative.exists():
            return alternative
    raise FileExistsError("无法为下载文件生成不冲突的名称。")


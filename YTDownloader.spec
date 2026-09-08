# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PySide6.QtCore import QLibraryInfo
from PyInstaller.utils.hooks import collect_all

root = Path(SPEC).resolve().parent
yt_datas, yt_bins, yt_hidden = collect_all("yt_dlp")
ejs_datas, ejs_bins, ejs_hidden = collect_all("yt_dlp_ejs")
qt_translations = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))

required = {
    "ffmpeg": root / "vendor" / "tools" / "ffmpeg" / "ffmpeg.exe",
    "ffprobe": root / "vendor" / "tools" / "ffmpeg" / "ffprobe.exe",
    "deno": root / "vendor" / "tools" / "deno" / "deno.exe",
}
missing = [name for name, path in required.items() if not path.is_file()]
if missing:
    raise SystemExit("Missing locked tools: " + ", ".join(missing) + ". Run scripts/prepare_tools.ps1 first.")

datas = yt_datas + ejs_datas + [
    (str(root / "assets"), "assets"),
    (str(root / "src" / "yt_downloader" / "ui" / "qml"), "yt_downloader/ui/qml"),
    (str(root / "licenses"), "third_party_licenses"),
    (str(root / "README.md"), "."),
    (str(root / "tools.lock.json"), "."),
    (str(qt_translations / "qtbase_zh_CN.qm"), "PySide6/translations"),
]
binaries = yt_bins + ejs_bins + [
    (str(required["ffmpeg"]), "tools/ffmpeg"),
    (str(required["ffprobe"]), "tools/ffmpeg"),
    (str(required["deno"]), "tools/deno"),
]
hiddenimports = yt_hidden + ejs_hidden + [
    "socks",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "yt_downloader.workers.metadata_process",
]

a = Analysis(
    [str(root / "src" / "yt_downloader" / "__main__.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# The desktop host may prepend document/PDF runtimes to PATH. Never let their
# unrelated native DLLs leak into this standalone application.
a.binaries = type(a.binaries)(
    entry for entry in a.binaries
    if "\\.cache\\codex-runtimes\\" not in str(entry[1]).lower()
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YTDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "assets" / "app.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="YTDownloader",
)

# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPEC).resolve().parent

a = Analysis(
    [str(root / 'src' / 'yt_downloader_updater' / '__main__.py')],
    pathex=[str(root / 'src')],
    binaries=[],
    datas=[],
    hiddenimports=['cryptography.hazmat.bindings._rust'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['PySide6', 'yt_dlp', 'PIL'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YTDownloaderUpdater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / 'assets' / 'app.ico'),
)

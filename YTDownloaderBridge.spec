# Native Messaging stdout is binary protocol; no Qt or yt-dlp runtime.
from pathlib import Path
root = Path(SPEC).resolve().parent
a = Analysis([str(root / 'src/yt_downloader/cli_browser_bridge.py')], pathex=[str(root / 'src')],
             binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[],
             excludes=['PySide6', 'yt_dlp', 'yt_dlp_ejs', 'curl_cffi'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='YTDownloaderBridge',
          debug=False, strip=False, upx=False, console=True)

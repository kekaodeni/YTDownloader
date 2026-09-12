import multiprocessing
import os
import sys
from pathlib import Path


_frozen_dll_handles = []


def _configure_frozen_dll_search_path() -> None:
    """Register PyInstaller's native dependency directories before Qt loads."""
    if not getattr(sys, "frozen", False):
        return
    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    for directory in (root, root / "PySide6", root / "shiboken6"):
        if not directory.is_dir():
            continue
        try:
            _frozen_dll_handles.append(os.add_dll_directory(str(directory)))
        except (AttributeError, OSError):
            pass


_configure_frozen_dll_search_path()
multiprocessing.freeze_support()

if "--self-test" in sys.argv[1:]:
    from yt_downloader.cli_self_test import main  # noqa: E402
elif "--metadata-helper-self-test-child" in sys.argv[1:]:
    from yt_downloader.cli_metadata_self_test import run_helper_child as main  # noqa: E402
elif "--metadata-process-self-test" in sys.argv[1:]:
    from yt_downloader.cli_metadata_self_test import main  # noqa: E402
else:
    from yt_downloader.app import main  # noqa: E402

raise SystemExit(main())

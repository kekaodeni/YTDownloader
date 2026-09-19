"""Bounded application logging and global exception reporting."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from typing import Callable
from yt_downloader.services.error_report_service import redact_sensitive


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_sensitive(super().format(record))


def configure_logging(log_directory: str | Path, *, debug: bool = False) -> Path:
    directory = Path(log_directory)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "yt-downloader.log"
    handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for old in tuple(root.handlers):
        root.removeHandler(old)
        old.close()
    root.addHandler(handler)
    logging.captureWarnings(True)
    return log_path


def install_exception_hook(callback: Callable[[BaseException, str], None] | None = None) -> None:
    previous = sys.excepthook

    def hook(exc_type, exc, tb) -> None:
        import traceback
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("yt_downloader.crash").critical("Unhandled exception\n%s", text)
        if callback:
            callback(exc, text)
        else:
            previous(exc_type, exc, tb)

    sys.excepthook = hook

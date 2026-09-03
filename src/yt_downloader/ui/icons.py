"""Single Fluent System Icons SVG provider."""

from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from yt_downloader.infrastructure.runtime import resource_path
class FluentIconService:
    """Loads the regular/filled SVG pair shipped under Microsoft's MIT license."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else resource_path("assets", "icons")
        self._cache: dict[tuple[str, bool, str], QIcon] = {}

    def icon(self, name: str, *, selected: bool = False, theme: str | None = None) -> QIcon:
        from yt_downloader.ui.theme import DARK, LIGHT

        if theme is None:
            app = QApplication.instance()
            theme = str(app.property("fluentTheme")) if app and app.property("fluentTheme") else "light"
        theme = "dark" if theme == "dark" else "light"
        key = (name, selected, theme)
        if key in self._cache:
            return self._cache[key]

        suffix = "filled" if selected else "regular"
        path = self.root / f"{name}_{suffix}.svg"
        tokens = DARK if theme == "dark" else LIGHT
        color = tokens.accent if selected else tokens.text_secondary
        svg = re.sub(r'fill="#[0-9A-Fa-f]{6}"', f'fill="{color}"', path.read_text(encoding="utf-8"))
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        icon = QIcon()
        for size in (16, 20, 24, 32, 40, 48):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pixmap)
        self._cache[key] = icon
        return icon

    @staticmethod
    def stylesheet_url(name: str, *, theme: str) -> str:
        """Return a QSS-safe URL for a pre-themed Fluent SVG resource."""
        resolved_theme = "dark" if theme == "dark" else "light"
        path = resource_path("assets", "icons", f"{name}_{resolved_theme}.svg")
        return f'url("{path.as_posix()}")'

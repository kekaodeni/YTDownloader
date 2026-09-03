"""Semantic Windows typography with whole-string script-aware font selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Iterable

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
)


class FontRole(StrEnum):
    PAGE_TITLE = "PageTitle"
    SECTION_TITLE = "SectionTitle"
    CARD_TITLE = "CardTitle"
    BODY = "Body"
    FORM_LABEL = "FormLabel"
    SECONDARY = "Secondary"
    TERTIARY = "Tertiary"
    BUTTON = "Button"
    NUMERIC = "Numeric"
    CAPTION = "Caption"


@dataclass(frozen=True, slots=True)
class FontFamilies:
    chinese: tuple[str, ...]
    japanese: tuple[str, ...]
    latin: tuple[str, ...]
    numeric: tuple[str, ...]

    @property
    def ui(self) -> tuple[str, ...]:
        """Compatibility alias for the application's Chinese-first body stack."""
        return self.chinese


@dataclass(frozen=True, slots=True)
class FontSpec:
    point_size: float
    weight: int


FONT_SPECS = {
    FontRole.PAGE_TITLE: FontSpec(16.5, 600),
    FontRole.SECTION_TITLE: FontSpec(13.5, 600),
    FontRole.CARD_TITLE: FontSpec(12.0, 600),
    FontRole.BODY: FontSpec(10.5, 400),
    FontRole.FORM_LABEL: FontSpec(10.5, 400),
    FontRole.SECONDARY: FontSpec(9.75, 400),
    FontRole.TERTIARY: FontSpec(9.0, 400),
    FontRole.BUTTON: FontSpec(10.5, 500),
    FontRole.NUMERIC: FontSpec(10.5, 400),
    FontRole.CAPTION: FontSpec(9.0, 400),
}

_CHINESE_CANDIDATES = ("Microsoft YaHei UI", "Microsoft YaHei")
_JAPANESE_CANDIDATES = ("Yu Gothic UI", "Meiryo")
_LATIN_CANDIDATES = ("Segoe UI Variable", "Segoe UI")
_NUMERIC_CANDIDATES = (
    "Segoe UI Variable",
    "Segoe UI",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
)
_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _available_stack(candidates: tuple[str, ...], available: set[str], fallback: str) -> tuple[str, ...]:
    ordered = [family for family in candidates if family in available]
    if fallback and fallback not in ordered:
        ordered.append(fallback)
    if not ordered:
        ordered.append("Sans Serif")
    return tuple(ordered)


def resolve_font_families(
    available: Iterable[str] | None = None,
    *,
    system_default: str = "",
) -> FontFamilies:
    installed = set(available if available is not None else QFontDatabase.families())
    fallback = system_default or QFont().defaultFamily()
    return FontFamilies(
        chinese=_available_stack(_CHINESE_CANDIDATES, installed, fallback),
        japanese=_available_stack(_JAPANESE_CANDIDATES, installed, fallback),
        latin=_available_stack(_LATIN_CANDIDATES, installed, fallback),
        numeric=_available_stack(_NUMERIC_CANDIDATES, installed, fallback),
    )


def _role_rule(role: FontRole) -> str:
    spec = FONT_SPECS[role]
    return (
        f'QWidget[typographyRole="{role.value}"] '
        f'{{ font-size: {spec.point_size:g}pt; font-weight: {spec.weight}; }}'
    )


def typography_qss(_families: FontFamilies | None = None) -> str:
    """Generate role sizing rules while leaving font-family to TypographyManager."""
    return "\n".join(_role_rule(role) for role in FontRole)


class TypographyManager:
    """Creates and applies QFonts from a semantic role and the complete text."""

    def __init__(self, families: FontFamilies | None = None) -> None:
        self.families = families or resolve_font_families()

    def family_stack(self, role: FontRole, text: str = "") -> tuple[str, ...]:
        if role is FontRole.NUMERIC:
            return self.families.numeric
        if _KANA.search(text):
            return self.families.japanese
        if _HAN.search(text):
            return self.families.chinese
        return self.families.latin

    def font_for(self, role: FontRole, text: str = "") -> QFont:
        spec = FONT_SPECS[role]
        font = QFont()
        font.setFamilies(list(self.family_stack(role, text)))
        font.setPointSizeF(spec.point_size)
        font.setWeight(QFont.Weight(spec.weight))
        return font

    def apply(self, widget: QWidget, role: FontRole, text: str | None = None) -> None:
        source = _widget_text(widget) if text is None else text
        widget.setProperty("typographyRole", role.value)
        widget.setFont(self.font_for(role, source))

    def apply_tree(self, root: QWidget) -> None:
        for widget in (root, *root.findChildren(QWidget)):
            role = _widget_role(widget)
            if role is not None:
                self.apply(widget, role)

    def set_text(self, widget: QWidget, text: str, role: FontRole | None = None) -> None:
        widget.setText(text)  # type: ignore[attr-defined]
        resolved = role or _widget_role(widget) or FontRole.BODY
        self.apply(widget, resolved, text)


def _widget_text(widget: QWidget) -> str:
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, (QLabel, QAbstractButton, QLineEdit, QAbstractSpinBox)):
        return widget.text()
    return ""


def _widget_role(widget: QWidget) -> FontRole | None:
    value = widget.property("typographyRole")
    if value:
        try:
            return FontRole(str(value))
        except ValueError:
            pass
    if isinstance(widget, QAbstractButton):
        return FontRole.BUTTON
    if isinstance(widget, (QLabel, QLineEdit, QComboBox, QAbstractSpinBox)):
        return FontRole.BODY
    return None


def install_typography_manager(
    app: QApplication,
    families: FontFamilies | None = None,
) -> TypographyManager:
    manager = TypographyManager(families or resolve_font_families(system_default=app.font().family()))
    setattr(app, "_yt_downloader_typography", manager)
    return manager


def typography_manager() -> TypographyManager:
    app = QApplication.instance()
    if app is not None:
        manager = getattr(app, "_yt_downloader_typography", None)
        if manager is None:
            manager = install_typography_manager(app)
        return manager
    return TypographyManager()


def apply_typography(widget: QWidget, role: FontRole, text: str | None = None) -> None:
    typography_manager().apply(widget, role, text)


def apply_typography_tree(root: QWidget) -> None:
    typography_manager().apply_tree(root)


def apply_form_typography(form: QFormLayout) -> None:
    manager = typography_manager()
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if item is not None and item.widget() is not None:
            manager.apply(item.widget(), FontRole.FORM_LABEL)


def set_typographic_text(widget: QWidget, text: str, role: FontRole | None = None) -> None:
    typography_manager().set_text(widget, text, role)


def sync_wrapped_label_height(label: QLabel) -> None:
    """Keep Qt layouts from squeezing a wrapping label below heightForWidth()."""
    if not label.wordWrap() or label.width() <= 0:
        return
    required = label.heightForWidth(label.width())
    if required >= 0 and label.minimumHeight() != required:
        label.setMinimumHeight(required)
        label.updateGeometry()


class WrappingLabel(QLabel):
    """A wrapping label whose minimum height follows its current width."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._height_sync_timer = QTimer(self)
        self._height_sync_timer.setSingleShot(True)
        self._height_sync_timer.timeout.connect(self._sync_height)
        self.setWordWrap(True)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Minimum)
        if text:
            self.setText(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        self._schedule_height_sync()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_height_sync()

    def _schedule_height_sync(self) -> None:
        self._height_sync_timer.start(0)

    def _sync_height(self) -> None:
        sync_wrapped_label_height(self)


def application_font(families: FontFamilies) -> QFont:
    spec = FONT_SPECS[FontRole.BODY]
    font = QFont()
    font.setFamilies(list(families.chinese))
    font.setPointSizeF(spec.point_size)
    font.setWeight(QFont.Weight.Normal)
    return font

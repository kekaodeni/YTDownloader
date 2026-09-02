"""Semantic Windows typography roles with Chinese and Latin fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from PySide6.QtGui import QFont, QFontDatabase


class FontRole(StrEnum):
    PAGE_TITLE = "PageTitle"
    SECTION_TITLE = "SectionTitle"
    BODY = "Body"
    SECONDARY = "Secondary"
    BUTTON = "Button"
    NUMERIC = "Numeric"
    CAPTION = "Caption"


@dataclass(frozen=True, slots=True)
class FontFamilies:
    ui: tuple[str, ...]
    numeric: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FontSpec:
    point_size: float
    weight: int
    family_group: str = "ui"


FONT_SPECS = {
    FontRole.PAGE_TITLE: FontSpec(22.0, 600),
    FontRole.SECTION_TITLE: FontSpec(14.5, 600),
    FontRole.BODY: FontSpec(10.5, 400),
    FontRole.SECONDARY: FontSpec(10.0, 400),
    FontRole.BUTTON: FontSpec(10.5, 500),
    FontRole.NUMERIC: FontSpec(10.0, 400, "numeric"),
    FontRole.CAPTION: FontSpec(9.0, 400),
}

_UI_CANDIDATES = (
    "Microsoft YaHei UI",
    "Segoe UI Variable",
    "Segoe UI",
    "Microsoft YaHei",
)
_NUMERIC_CANDIDATES = (
    "Segoe UI Variable",
    "Segoe UI",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
)


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
        ui=_available_stack(_UI_CANDIDATES, installed, fallback),
        numeric=_available_stack(_NUMERIC_CANDIDATES, installed, fallback),
    )


def _family_qss(values: tuple[str, ...]) -> str:
    return ", ".join(f'"{value}"' for value in values)


def _role_rule(selector: str, role: FontRole, families: FontFamilies) -> str:
    spec = FONT_SPECS[role]
    stack = families.numeric if spec.family_group == "numeric" else families.ui
    return (
        f"{selector} {{ font-family: {_family_qss(stack)}; "
        f"font-size: {spec.point_size:g}pt; font-weight: {spec.weight}; }}"
    )


def typography_qss(families: FontFamilies) -> str:
    return "\n".join((
        _role_rule(
            f'QLabel[headingLevel="1"], QWidget[typographyRole="{FontRole.PAGE_TITLE.value}"]',
            FontRole.PAGE_TITLE,
            families,
        ),
        _role_rule(
            f'QLabel[headingLevel="2"], QWidget[typographyRole="{FontRole.SECTION_TITLE.value}"]',
            FontRole.SECTION_TITLE,
            families,
        ),
        _role_rule(
            f'QWidget[typographyRole="{FontRole.BODY.value}"]',
            FontRole.BODY,
            families,
        ),
        _role_rule(
            f'QLabel[secondary="true"], QWidget[typographyRole="{FontRole.SECONDARY.value}"]',
            FontRole.SECONDARY,
            families,
        ),
        _role_rule(
            f'QPushButton, QToolButton, QWidget[typographyRole="{FontRole.BUTTON.value}"]',
            FontRole.BUTTON,
            families,
        ),
        _role_rule(
            f'QWidget[typographyRole="{FontRole.NUMERIC.value}"]',
            FontRole.NUMERIC,
            families,
        ),
        _role_rule(
            f'QWidget[typographyRole="{FontRole.CAPTION.value}"]',
            FontRole.CAPTION,
            families,
        ),
        _role_rule('QLabel[headingLevel="3"]', FontRole.BODY, families).replace(
            "font-weight: 400", "font-weight: 600"
        ),
    ))


def application_font(families: FontFamilies) -> QFont:
    spec = FONT_SPECS[FontRole.BODY]
    font = QFont(families.ui[0])
    font.setPointSizeF(spec.point_size)
    font.setWeight(QFont.Weight.Normal)
    return font

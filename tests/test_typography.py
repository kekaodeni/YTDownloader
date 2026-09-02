from PySide6.QtGui import QFont

from yt_downloader.ui.typography import (
    FontRole,
    application_font,
    resolve_font_families,
    typography_qss,
)
from yt_downloader.ui.widgets.progress_widget import ProgressWidget


def test_font_resolution_prefers_chinese_ui_and_segoe_for_numeric_content() -> None:
    families = resolve_font_families({
        "Segoe UI",
        "Microsoft YaHei",
        "Microsoft YaHei UI",
        "Segoe UI Variable",
    }, system_default="Fallback")

    assert families.ui[0] == "Microsoft YaHei UI"
    assert families.numeric[0] == "Segoe UI Variable"
    assert families.ui[-1] == "Fallback"


def test_semantic_qss_defines_all_typography_roles_without_wildcard_font_override() -> None:
    families = resolve_font_families({"Microsoft YaHei UI", "Segoe UI"}, system_default="Fallback")
    stylesheet = typography_qss(families)

    for role in FontRole:
        assert f'typographyRole="{role.value}"' in stylesheet
    assert "* { font-family" not in stylesheet
    assert 'font-family: "Microsoft YaHei UI"' in stylesheet
    assert 'font-family: "Segoe UI"' in stylesheet


def test_application_body_font_uses_resolved_ui_family() -> None:
    families = resolve_font_families({"Microsoft YaHei UI", "Segoe UI"}, system_default="Fallback")

    font = application_font(families)

    assert isinstance(font, QFont)
    assert font.family() == "Microsoft YaHei UI"
    assert font.pointSizeF() == 10.5


def test_progress_numbers_use_numeric_semantic_role(qtbot) -> None:
    widget = ProgressWidget()
    qtbot.addWidget(widget)

    for label in (widget.percent_label, widget.speed_label, widget.size_label, widget.eta_label):
        assert label.property("typographyRole") == FontRole.NUMERIC.value

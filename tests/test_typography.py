from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel

from yt_downloader.ui.typography import (
    FONT_SPECS,
    FontRole,
    TypographyManager,
    application_font,
    resolve_font_families,
    typography_qss,
)


def test_font_resolution_has_script_specific_windows_fallbacks() -> None:
    families = resolve_font_families({
        "Meiryo",
        "Segoe UI",
        "Microsoft YaHei",
        "Microsoft YaHei UI",
        "Segoe UI Variable",
        "Yu Gothic UI",
        "Malgun Gothic",
        "Segoe UI Emoji",
    }, system_default="Fallback")

    assert families.chinese[:2] == ("Microsoft YaHei UI", "Microsoft YaHei")
    assert families.japanese[:2] == ("Yu Gothic UI", "Meiryo")
    assert families.latin[:2] == ("Segoe UI", "Segoe UI Variable")
    assert families.korean[0] == "Malgun Gothic"
    assert families.emoji[0] == "Segoe UI Emoji"
    assert families.numeric[0] == "Segoe UI"
    assert all(stack[-1] == "Fallback" for stack in (
        families.chinese,
        families.japanese,
        families.latin,
        families.numeric,
        families.korean,
        families.emoji,
    ))


def test_semantic_font_roles_use_the_approved_sizes_and_weights() -> None:
    expected = {
        FontRole.PAGE_TITLE: (16.5, 400),
        FontRole.SECTION_TITLE: (12.0, 700),
        FontRole.CARD_TITLE: (11.25, 400),
        FontRole.BODY: (10.5, 400),
        FontRole.FORM_LABEL: (10.5, 400),
        FontRole.SECONDARY: (9.75, 400),
        FontRole.TERTIARY: (9.0, 400),
        FontRole.BUTTON: (10.5, 400),
        FontRole.NUMERIC: (10.5, 400),
        FontRole.CAPTION: (9.0, 400),
    }

    assert {role: (spec.point_size, spec.weight) for role, spec in FONT_SPECS.items()} == expected


def test_semantic_qss_has_one_role_driven_hierarchy_without_family_override() -> None:
    families = resolve_font_families({"Microsoft YaHei UI", "Segoe UI"}, system_default="Fallback")
    stylesheet = typography_qss(families)

    for role in FontRole:
        assert f'typographyRole="{role.value}"' in stylesheet
    assert "* { font-family" not in stylesheet
    assert "font-family" not in stylesheet


def test_application_body_font_uses_resolved_ui_family() -> None:
    families = resolve_font_families({"Microsoft YaHei UI", "Segoe UI"}, system_default="Fallback")

    font = application_font(families)

    assert isinstance(font, QFont)
    assert font.family() == "Microsoft YaHei UI"
    assert font.pointSizeF() == 10.5


def test_typography_manager_selects_one_stack_for_the_complete_text() -> None:
    families = resolve_font_families({
        "Meiryo",
        "Microsoft YaHei",
        "Microsoft YaHei UI",
        "Segoe UI",
        "Segoe UI Variable",
        "Yu Gothic UI",
        "Malgun Gothic",
        "Segoe UI Emoji",
    }, system_default="Fallback")
    manager = TypographyManager(families)

    assert manager.family_stack(FontRole.CARD_TITLE, "下载视频 🚀")[0] == "Microsoft YaHei UI"
    assert manager.family_stack(FontRole.CARD_TITLE, "桜のテスト動画 🚀")[0] == "Microsoft YaHei UI"
    assert manager.family_stack(FontRole.CARD_TITLE, "Download 1080p 🚀")[0] == "Segoe UI"
    assert manager.family_stack(FontRole.CARD_TITLE, "다운로드 영상")[0] == "Malgun Gothic"
    assert manager.family_stack(FontRole.CARD_TITLE, "🚀🎬")[0] == "Segoe UI Emoji"
    assert manager.family_stack(FontRole.NUMERIC, "剩余 10 秒")[0] == "Segoe UI"


def test_dynamic_text_reapplies_its_role_with_the_new_script_font(qtbot) -> None:
    families = resolve_font_families({
        "Meiryo",
        "Microsoft YaHei UI",
        "Segoe UI Variable",
        "Yu Gothic UI",
    }, system_default="Fallback")
    manager = TypographyManager(families)
    label = QLabel("下载视频")
    qtbot.addWidget(label)

    manager.apply(label, FontRole.CARD_TITLE)
    assert label.font().families()[0] == "Microsoft YaHei UI"

    manager.set_text(label, "桜のテスト動画", FontRole.CARD_TITLE)
    assert label.property("typographyRole") == FontRole.CARD_TITLE.value
    assert label.font().families()[0] == "Microsoft YaHei UI"
    assert label.font().pointSizeF() == 11.25
    assert label.font().weight() == QFont.Weight.Normal


def _contrast_ratio(first: QColor, second: QColor) -> float:
    def luminance(color: QColor) -> float:
        channels = []
        for value in (color.redF(), color.greenF(), color.blueF()):
            channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_theme_tokens_use_semantic_non_absolute_text_and_readable_contrast(quick_window):
    for mode in ('light','dark'):
        quick_window.theme.set_mode(mode)
        tokens=quick_window.theme.state
        assert tokens['text'].upper() not in {'#000000','#FFFFFF'}
        for key in ('text','secondary','muted'):
            assert _contrast_ratio(QColor(tokens[key]),QColor(tokens['canvas'])) >= 4.5


def test_progress_numbers_use_numeric_semantic_role(quick_window):
    font=quick_window.theme.fontFor('Numeric','剩余 10 秒')
    assert font.pointSizeF()==10.5
    assert font.families()==list(quick_window.theme.typography.family_stack(FontRole.NUMERIC,'剩余 10 秒'))


def test_empty_field_uses_placeholder_script_and_latin_has_cjk_fallback(quick_window):
    from conftest import find_item
    field = find_item(quick_window, 'urlInput')
    assert not field.property('text')
    assert field.property('font').families()[0] == 'Microsoft YaHei UI'
    field.setProperty('text', 'https://example.invalid')
    assert field.property('font').families()[0] == 'Segoe UI'
    assert 'Microsoft YaHei UI' in field.property('font').families()
    field.setProperty('text', '')
    assert field.property('font').families()[0] == 'Microsoft YaHei UI'

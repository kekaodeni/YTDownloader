"""Semantic Fluent 2 light/dark tokens, QPalette and one generated QSS."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from yt_downloader.ui.typography import FontFamilies, resolve_font_families, typography_qss


@dataclass(frozen=True, slots=True)
class FluentTokens:
    canvas: str
    card: str
    elevated: str
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_disabled: str
    stroke: str
    stroke_focus: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    danger: str
    selection: str
    selection_hover: str
    surface_tint: str
    surface_subtle: str
    surface_highlight: str

    @property
    def background(self) -> str:
        return self.canvas

    @property
    def layer(self) -> str:
        return self.card

    @property
    def layer_alt(self) -> str:
        return self.elevated

    @property
    def text(self) -> str:
        return self.text_primary


LIGHT = FluentTokens(
    canvas="#F5F5F5", card="#FFFFFF", elevated="#FAFAFA",
    text_primary="#242424", text_secondary="#5D5D5D", text_tertiary="#6B6B6B", text_disabled="#9E9E9E",
    stroke="#D1D1D1", stroke_focus="#0067C0", accent="#0067C0",
    accent_hover="#1975C5", accent_pressed="#005A9E", accent_text="#FFFFFF",
    danger="#C42B1C", selection="#DDEAF7", selection_hover="#C9DFF2",
    surface_tint="rgba(255, 255, 255, 238)", surface_subtle="rgba(255, 255, 255, 168)",
    surface_highlight="#FFFFFF",
)
DARK = FluentTokens(
    canvas="#202020", card="#2B2B2B", elevated="#323232",
    text_primary="#F2F2F2", text_secondary="#C7C7C7", text_tertiary="#ADADAD", text_disabled="#777777",
    stroke="#4A4A4A", stroke_focus="#60CDFF", accent="#60CDFF",
    accent_hover="#75D4FF", accent_pressed="#4CC2FF", accent_text="#102027",
    danger="#FF99A4", selection="#153B52", selection_hover="#234C63",
    surface_tint="rgba(45, 45, 45, 238)", surface_subtle="rgba(255, 255, 255, 10)",
    surface_highlight="#525252",
)


def _qss(t: FluentTokens, fonts: FontFamilies | None = None) -> str:
    fonts = fonts or resolve_font_families()
    return f"""
    * {{ color: {t.text_primary}; }}
    QMainWindow, QDialog {{ background: {t.canvas}; }}
    QWidget#navigationRail {{ background: {t.elevated}; border-right: 1px solid {t.stroke}; }}
    QWidget[fluentRole="card"] {{ background: {t.surface_tint}; border: 1px solid {t.stroke}; border-radius: 10px; }}
    QWidget[fluentRole="subtle"] {{ background: {t.surface_subtle}; border: 1px solid {t.surface_highlight}; border-radius: 8px; }}
    QWidget[typographyRole="Secondary"] {{ color: {t.text_secondary}; }}
    QWidget[typographyRole="Tertiary"], QWidget[typographyRole="Caption"] {{ color: {t.text_tertiary}; }}
    QLabel[error="true"] {{ color: {t.danger}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {t.card}; border: 1px solid {t.stroke}; border-bottom: 2px solid {t.stroke};
        border-radius: 6px; padding: 7px 10px; min-height: 20px; selection-background-color: {t.selection};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {t.text_secondary}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-bottom-color: {t.stroke_focus}; }}
    QComboBox QAbstractItemView {{
        background: {t.card}; color: {t.text_primary}; border: 1px solid {t.stroke};
        border-radius: 8px; outline: none; padding: 4px;
        selection-background-color: {t.selection}; selection-color: {t.text_primary};
    }}
    QComboBox QAbstractItemView:focus {{ border: 1px solid {t.stroke_focus}; }}
    QComboBox QAbstractItemView::item {{
        background: {t.card}; color: {t.text_primary}; border: none; border-radius: 6px;
        min-height: 28px; padding: 7px 10px; margin: 1px;
    }}
    QComboBox QAbstractItemView::item:hover {{ background: {t.elevated}; color: {t.text_primary}; }}
    QComboBox QAbstractItemView::item:selected {{ background: {t.selection}; color: {t.text_primary}; }}
    QComboBox QAbstractItemView::item:selected:hover {{ background: {t.selection_hover}; color: {t.text_primary}; }}
    QComboBox QAbstractItemView::item:disabled {{ background: {t.card}; color: {t.text_disabled}; }}
    QPushButton, QToolButton {{
        background: {t.card}; border: 1px solid {t.stroke}; border-radius: 6px;
        padding: 7px 14px; min-height: 20px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {t.elevated}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {t.selection}; }}
    QPushButton:focus, QToolButton:focus {{ border: 2px solid {t.stroke_focus}; padding: 6px 13px; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {t.text_disabled}; border-color: {t.stroke}; }}
    QLineEdit QToolButton {{
        background: transparent; border: none; border-radius: 4px;
        padding: 0; margin: 0; min-width: 20px; min-height: 0;
        qproperty-iconSize: 16px 16px;
    }}
    QLineEdit QToolButton:hover {{ background: {t.elevated}; border: none; }}
    QLineEdit QToolButton:pressed {{ background: {t.selection}; border: none; }}
    QLineEdit QToolButton:focus {{ border: none; padding: 0; }}
    QPushButton[fluentAppearance="primary"] {{ background: {t.accent}; color: {t.accent_text}; border-color: {t.accent}; }}
    QPushButton[fluentAppearance="primary"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton[fluentAppearance="primary"]:pressed {{ background: {t.accent_pressed}; border-color: {t.accent_pressed}; }}
    QPushButton[fluentAppearance="danger"] {{ color: {t.danger}; }}
    QToolButton[navSelected="true"] {{ background: {t.selection}; border-color: transparent; }}
    QProgressBar {{ background: {t.elevated}; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
    QListView {{ background: transparent; border: none; outline: none; padding: 2px; }}
    QListView::item {{ background: {t.card}; border: 1px solid {t.stroke}; border-radius: 8px; padding: 12px; margin: 4px 0; }}
    QListView::item:selected {{ background: {t.selection}; border-color: {t.stroke_focus}; }}
    QListView::item:hover {{ background: {t.elevated}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.stroke}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QFrame[separator="true"] {{ background: {t.stroke}; max-height: 1px; }}
    QToolTip {{ background: {t.card}; color: {t.text_primary}; border: 1px solid {t.stroke}; padding: 5px; }}
    QMenu {{ background: {t.card}; color: {t.text_primary}; border: 1px solid {t.stroke}; padding: 5px; }}
    QMenu::item {{ background: transparent; color: {t.text_primary}; border-radius: 5px; padding: 7px 24px 7px 10px; }}
    QMenu::item:selected {{ background: {t.selection}; color: {t.text_primary}; }}
    QMenu::item:disabled {{ color: {t.text_disabled}; }}
    QMenu::separator {{ background: {t.stroke}; height: 1px; margin: 5px 8px; }}
    """ + typography_qss(fonts)


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.mode = "system"
        self.resolved_mode = "light"
        self.fonts = resolve_font_families(system_default=app.font().family())
        hints = app.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._system_changed)

    def set_mode(self, mode: str) -> None:
        if mode not in {"system", "light", "dark"}:
            raise ValueError("Unsupported theme mode")
        self.mode = mode
        self._apply()

    def _system_changed(self, _scheme) -> None:
        if self.mode == "system":
            self._apply()

    def _is_system_dark(self) -> bool:
        return self.app.styleHints().colorScheme() == Qt.ColorScheme.Dark

    def _apply(self) -> None:
        self.resolved_mode = "dark" if self.mode == "dark" or (self.mode == "system" and self._is_system_dark()) else "light"
        tokens = DARK if self.resolved_mode == "dark" else LIGHT
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(tokens.canvas))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens.card))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.elevated))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.Button, QColor(tokens.card))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.selection))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.text_primary))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(tokens.text_secondary))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(tokens.text_disabled))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(tokens.text_disabled))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(tokens.text_disabled))
        self.app.setPalette(palette)
        self.app.setStyleSheet(_qss(tokens, self.fonts))
        self.app.setProperty("fluentTheme", self.resolved_mode)
        self.theme_changed.emit(self.resolved_mode)

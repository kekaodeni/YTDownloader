"""One semantic palette and the existing script-aware typography for Qt Quick."""
from PySide6.QtCore import QObject, Property, Qt, Signal, Slot
from PySide6.QtGui import QFont, QPalette, QColor

from yt_downloader.ui.quick_state import ViewState
from yt_downloader.ui.typography import (
    FONT_SPECS,
    FontRole,
    TypographyManager,
    _CHINESE_CANDIDATES,
    _EMOJI_CANDIDATES,
    _JAPANESE_CANDIDATES,
    _KOREAN_CANDIDATES,
    _LATIN_CANDIDATES,
    _NUMERIC_CANDIDATES,
    resolve_font_families,
)


class QuickTheme(ViewState):
    theme_changed = Signal(str)

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.mode = 'system'
        self.resolved_mode = 'light'
        # Quick/QML tests and packaged rendering use the same semantic family
        # contract even when the host's offscreen font database is empty.
        semantic_families = set(
            _CHINESE_CANDIDATES + _EMOJI_CANDIDATES + _JAPANESE_CANDIDATES
            + _KOREAN_CANDIDATES + _LATIN_CANDIDATES + _NUMERIC_CANDIDATES
        )
        self.typography = TypographyManager(resolve_font_families(semantic_families))
        app.styleHints().colorSchemeChanged.connect(lambda _: self._apply() if self.mode == 'system' else None)
        self._apply()

    @Slot(str)
    def set_mode(self, mode):
        self.mode = mode
        self._apply()

    def _apply(self):
        dark = self.mode == 'dark' or (self.mode == 'system' and self.app.styleHints().colorScheme() is Qt.ColorScheme.Dark)
        self.resolved_mode = 'dark' if dark else 'light'
        colors = dict(dark=dark, canvas='#171A20' if dark else '#F4F6F9',
                      sidebar='#1D2027' if dark else '#EBEEF3', surface='#22262E' if dark else '#FFFFFF',
                      elevated='#2A2F39' if dark else '#FFFFFF', subtle='#2D323C' if dark else '#F0F3F8',
                      text='#EDF0F6' if dark else '#1C2433', secondary='#B3BBCB' if dark else '#58657A',
                      muted='#9AA5B7' if dark else '#657188', disabled='#737D8D' if dark else '#8792A3',
                      stroke='#3D4553' if dark else '#DCE2EB', accent='#79B8FF' if dark else '#1768CE',
                      accentHover='#98C9FF' if dark else '#2377DD', onAccent='#10253F' if dark else '#FFFFFF',
                      selection='#293E59' if dark else '#DDEBFD', danger='#FF9FA8' if dark else '#B5293D',
                      success='#8DDBB0' if dark else '#23744B')
        # Native file pickers and Qt accessibility use the same broad palette.
        palette = QPalette()
        for role, key in ((QPalette.ColorRole.Window, 'canvas'), (QPalette.ColorRole.Base, 'surface'),
                          (QPalette.ColorRole.Text, 'text'), (QPalette.ColorRole.WindowText, 'text'),
                          (QPalette.ColorRole.Button, 'surface'), (QPalette.ColorRole.ButtonText, 'text'),
                          (QPalette.ColorRole.Highlight, 'selection'), (QPalette.ColorRole.HighlightedText, 'text')):
            palette.setColor(role, QColor(colors[key]))
        self.app.setPalette(palette)
        self.update(**colors)
        self.theme_changed.emit(self.resolved_mode)

    @Slot(str, str, result=QFont)
    def fontFor(self, role, text):
        return self.typography.font_for(FontRole(role), text)

    @Slot(str, str, result=str)
    def fontFamily(self, role, text):
        """Return the first semantic family for direct QML font binding.

        Passing a Python QFont through a QML font property makes Qt resolve
        the whole fallback stack against the host font database. Binding the
        selected family as a QML string keeps the application's typography
        contract deterministic while preserving the Python fallback stack for
        widgets and direct callers.
        """
        return self.typography.preferred_family(FontRole(role), text)

    @Slot(str, result=float)
    def fontSize(self, role):
        return FONT_SPECS[FontRole(role)].point_size

    @Slot(str, result=int)
    def fontWeight(self, role):
        return FONT_SPECS[FontRole(role)].weight

    @Slot(QObject, str, str)
    def applyFont(self, item, role, text):
        """Apply the complete fallback stack after a QML text edit.

        QML's declarative family binding is used for deterministic initial
        display. An imperative update keeps the complete Python fallback stack
        when the text changes, which is needed for mixed Latin/CJK input.
        """
        if item is not None:
            item.setProperty('font', self.typography.font_for(FontRole(role), text))

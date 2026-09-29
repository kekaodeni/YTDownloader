"""Single-catalog, live localization service for Python and Qt Quick UI."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
import json
import re
from importlib.resources import files
from string import Formatter

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QObject, Property, QTranslator, Signal, Slot
from PySide6.QtWidgets import QDialogButtonBox
from yt_downloader.core.models import SUPPORTED_LOCALES


ACTION_TEXT = MappingProxyType({
    "cancel": "取消",
    "ok": "确定",
    "close": "关闭",
    "retry": "重试",
    "open": "打开",
    "delete": "删除",
})

_STANDARD_ACTIONS = {
    QDialogButtonBox.StandardButton.Cancel: "cancel",
    QDialogButtonBox.StandardButton.Ok: "ok",
    QDialogButtonBox.StandardButton.Close: "close",
    QDialogButtonBox.StandardButton.Retry: "retry",
    QDialogButtonBox.StandardButton.Open: "open",
}


class Translator(QObject):
    """Expose one message catalog to Python presentation code and QML."""

    languageChanged = Signal(str)
    catalogChanged = Signal()
    currentLocaleChanged = Signal()

    def __init__(self, locale: str = 'zh-CN', parent=None):
        super().__init__(parent)
        catalog_path = files('yt_downloader.ui').joinpath('translations.json')
        self._catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
        self._languages = tuple(self._catalog['languages'])
        self._supported = set(SUPPORTED_LOCALES)
        self._locale = 'zh-CN'
        self.setLanguage(locale)

    @Property(str, notify=currentLocaleChanged)
    def currentLocale(self):
        return self._locale

    @Property('QVariantList', constant=True)
    def languages(self):
        return list(self._languages)

    @Property('QVariantMap', notify=catalogChanged)
    def messages(self):
        return {message_id: values[self._locale]
                for message_id, values in self._catalog['messages'].items()
                if self._locale in values}

    @Slot(str)
    def setLanguage(self, locale: str):
        locale = str(locale)
        if locale not in self._supported or locale == self._locale:
            return
        self._locale = locale
        self.currentLocaleChanged.emit()
        self.catalogChanged.emit()
        self.languageChanged.emit(locale)

    @Slot(str, result=str)
    @Slot(str, 'QVariant', result=str)
    def text(self, message_id: str, parameters=None) -> str:
        """Return the active locale value; expose gaps rather than hiding them."""
        message = self._catalog['messages'].get(str(message_id))
        if message is None or self._locale not in message:
            return f'[missing:{message_id}]'
        value = str(message[self._locale])
        if parameters:
            try:
                return value.format_map({str(key): value for key, value in dict(parameters).items()})
            except (KeyError, ValueError):
                return f'[missing-parameter:{message_id}]'
        return value

    @Slot(str, result=str)
    def sourceText(self, source: str) -> str:
        """Translate a legacy zh-CN presentation string through the one catalog.

        Existing controller callbacks still produce source-language sentences.
        This adapter keeps them on the shared catalog while those call sites are
        gradually moved to explicit message IDs.
        """
        source = str(source)
        matches = []
        for message_id, values in self._catalog['messages'].items():
            template = str(values.get('zh-CN', ''))
            if not template:
                continue
            fields = []
            pieces = []
            last = 0
            for _, field_name, _, _ in Formatter().parse(template):
                if field_name is None:
                    continue
                start = template.find('{' + field_name + '}', last)
                if start < 0:
                    continue
                pieces.append(re.escape(template[last:start]))
                pieces.append('(.*?)')
                fields.append(field_name)
                last = start + len(field_name) + 2
            if not fields:
                if source == template:
                    matches.append((len(template), message_id, {}))
                continue
            pieces.append(re.escape(template[last:]))
            found = re.fullmatch(''.join(pieces), source, flags=re.DOTALL)
            if found:
                matches.append((len(template), message_id, dict(zip(fields, found.groups()))))
        if not matches:
            return source
        _, message_id, parameters = max(matches, key=lambda item: item[0])
        return self.text(message_id, parameters)

    @Slot(result='QVariantList')
    def validateCoverage(self):
        missing = []
        for message_id, values in self._catalog['messages'].items():
            reference_fields = None
            for locale, text in values.items():
                try:
                    fields = tuple(sorted(name for _, name, _, _ in Formatter().parse(str(text)) if name))
                except ValueError:
                    missing.append(f'{locale}:{message_id}:invalid-placeholder')
                    continue
                if reference_fields is None:
                    reference_fields = fields
                elif fields != reference_fields:
                    missing.append(f'{locale}:{message_id}:placeholder-mismatch')
            for locale in self._supported:
                if locale not in values or not str(values[locale]).strip():
                    missing.append(f'{locale}:{message_id}')
        return missing


def action_text(action: str) -> str:
    """Return a stable Simplified Chinese label for an application action."""
    return ACTION_TEXT[action]


def localize_dialog_button_box(button_box: QDialogButtonBox) -> None:
    """Localize standard buttons without depending on the host OS language."""
    for standard_button, action in _STANDARD_ACTIONS.items():
        button = button_box.button(standard_button)
        if button is not None:
            button.setText(action_text(action))


def install_qt_zh_cn_translator(app: QCoreApplication) -> bool:
    """Install PySide6's official zh_CN translation as a native-widget fallback."""
    translations = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    for filename in ("qtbase_zh_CN.qm", "qt_zh_CN.qm"):
        translator = QTranslator(app)
        if translator.load(str(translations / filename)):
            app.installTranslator(translator)
            installed = getattr(app, "_yt_downloader_translators", [])
            installed.append(translator)
            setattr(app, "_yt_downloader_translators", installed)
            return True
    return False

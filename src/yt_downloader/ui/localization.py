"""Small, deterministic localization helpers for application-owned dialogs."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTranslator
from PySide6.QtWidgets import QDialogButtonBox


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

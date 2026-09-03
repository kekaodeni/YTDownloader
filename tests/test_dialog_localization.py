from pathlib import Path

from PySide6.QtWidgets import QPushButton

from yt_downloader.core.errors import AppError
from yt_downloader.ui.widgets.confirm_dialog import (
    DeleteHistoryBatchDialog,
    DeleteHistoryDialog,
    IncompleteCleanupDialog,
    RemoveActiveTaskDialog,
)
from yt_downloader.ui.widgets.error_dialog import ErrorDialog
from yt_downloader.ui.widgets.thumbnail_dialog import ThumbnailDialog
from yt_downloader.ui.localization import ACTION_TEXT, install_qt_zh_cn_translator


class _ImmediateThumbnailService:
    def probe_duration(self, _media: Path, **_kwargs) -> float:
        return 2.0


def _button_texts(dialog) -> set[str]:
    return {
        button.text().replace("&", "")
        for button in dialog.findChildren(QPushButton)
    }


def test_all_application_dialog_actions_are_localized(qtbot, tmp_path: Path) -> None:
    media = tmp_path / "视频.mp4"
    media.write_bytes(b"test-media")
    dialogs = [
        DeleteHistoryDialog("测试记录"),
        DeleteHistoryBatchDialog(2),
        RemoveActiveTaskDialog("测试任务"),
        IncompleteCleanupDialog(),
        ErrorDialog(AppError("test", "用户说明", "技术详情"), "safe report"),
        ThumbnailDialog(
            media,
            "video-id",
            tmp_path / "preview-cache",
            _ImmediateThumbnailService(),  # type: ignore[arg-type]
        ),
    ]
    for dialog in dialogs:
        qtbot.addWidget(dialog)
    qtbot.waitUntil(dialogs[-1].preview_button.isEnabled, timeout=1000)

    english_actions = {"Cancel", "OK", "Close", "Retry", "Open", "Delete"}
    for dialog in dialogs:
        assert _button_texts(dialog).isdisjoint(english_actions)

    assert "取消" in _button_texts(dialogs[0])
    assert "取消" in _button_texts(dialogs[1])
    assert "关闭" in _button_texts(dialogs[4])
    assert "取消" in _button_texts(dialogs[5])


def test_action_map_covers_required_dialog_verbs() -> None:
    assert ACTION_TEXT == {
        "cancel": "取消",
        "ok": "确定",
        "close": "关闭",
        "retry": "重试",
        "open": "打开",
        "delete": "删除",
    }


def test_qt_simplified_chinese_translation_is_available(qapp) -> None:
    assert install_qt_zh_cn_translator(qapp)

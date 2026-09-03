from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication, QMenu

from yt_downloader.core.models import TaskStatus
from yt_downloader.ui.pages.history_page import HistoryPage
from test_history_repository import _record


def _action(menu: QMenu, text: str):
    return next(action for action in menu.actions() if action.text() == text)


def test_context_menu_selects_pointer_record_and_has_all_actions(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = HistoryPage()
    qtbot.addWidget(page)
    page.resize(760, 520)
    page.show()
    records = [
        _record(tmp_path, "first", TaskStatus.COMPLETED),
        _record(tmp_path, "second", TaskStatus.FAILED),
    ]
    records[1].file_path.write_bytes(b"keep")
    page.set_records(records)
    captured: list[QMenu] = []
    monkeypatch.setattr(page, "_exec_context_menu", lambda menu, _global: captured.append(menu))
    second_index = page.model.index(1, 0)
    point = page.list_view.visualRect(second_index).center()

    QApplication.sendEvent(
        page.list_view.viewport(),
        QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            point,
            page.list_view.viewport().mapToGlobal(point),
        ),
    )

    assert page.selected_record().task_id == "second"  # type: ignore[union-attr]
    assert captured
    assert [action.text() for action in captured[0].actions()] == [
        "打开文件", "打开文件夹", "复制链接", "重新下载", "设置视频封面", "", "删除记录",
    ]


def test_delete_action_requires_confirmation_and_is_disabled_for_active_task(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = HistoryPage()
    qtbot.addWidget(page)
    terminal = _record(tmp_path, "done", TaskStatus.COMPLETED)
    active = _record(tmp_path, "active", TaskStatus.DOWNLOADING_VIDEO)
    monkeypatch.setattr(page, "_confirm_delete_record", lambda _record: True)

    with qtbot.waitSignal(page.delete_requested, timeout=500) as signal:
        _action(page._build_context_menu(terminal), "删除记录").trigger()

    assert signal.args[0].task_id == "done"
    assert not _action(page._build_context_menu(active), "删除记录").isEnabled()


def test_shift_f10_opens_context_menu_for_keyboard_selection(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = HistoryPage()
    qtbot.addWidget(page)
    page.resize(760, 520)
    page.show()
    page.set_records([_record(tmp_path, "keyboard", TaskStatus.COMPLETED)])
    page.list_view.setCurrentIndex(page.model.index(0, 0))
    captured: list[QMenu] = []
    monkeypatch.setattr(page, "_exec_context_menu", lambda menu, _global: captured.append(menu))

    qtbot.keyClick(page.list_view, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)

    assert captured
    assert _action(captured[0], "复制链接").isEnabled()

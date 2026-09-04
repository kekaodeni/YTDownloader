from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMenu, QPushButton, QVBoxLayout, QWidget

from yt_downloader.ui.motion import MotionManager


def test_dialog_input_settles_appearance_then_accepts_exactly_once(qapp, qtbot):
    root = QWidget()
    qtbot.addWidget(root)
    root.show()
    manager = MotionManager(parent=root)
    dialog = QDialog(root)
    layout = QVBoxLayout(dialog)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    results = []
    dialog.accepted.connect(lambda: results.append('accepted'))
    dialog.show()
    assert dialog.windowOpacity() < 1
    qtbot.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
    assert results == ['accepted']
    assert dialog.windowOpacity() == 1


def test_menu_appearance_is_cleaned_when_popup_closes(qapp, qtbot):
    root = QWidget()
    qtbot.addWidget(root)
    root.show()
    manager = MotionManager(parent=root)
    menu = QMenu(root)
    menu.addAction('删除')
    menu.popup(root.mapToGlobal(QPoint(0, 0)))
    assert menu.windowOpacity() < 1
    menu.close()
    assert menu.windowOpacity() == 1
    assert manager.active_window_count == 0

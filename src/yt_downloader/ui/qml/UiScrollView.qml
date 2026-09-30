import QtQuick.Controls.Basic

// Fixed content reserve; hover/drag only changes the inner thumb.
ScrollView {
    rightPadding: 20
    ScrollBar.vertical: UiScrollBar { }
}

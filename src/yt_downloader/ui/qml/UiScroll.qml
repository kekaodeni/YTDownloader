import QtQuick
import QtQuick.Controls.Basic

Flickable {
    id: root
    clip: true
    contentWidth: width
    readonly property int contentInsetRight: scrollbar.width + scrollbar.edgeInset + 4
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    ScrollBar.vertical: UiScrollBar {
        id: scrollbar
        onPressedChanged: if (pressed) wheel.stop()
    }
    Keys.priority: Keys.AfterItem
    Keys.onPressed: function(event) {
        const top = root.originY
        const bottom = top + Math.max(0, root.contentHeight - root.height)
        if (event.key === Qt.Key_PageDown || event.key === Qt.Key_PageUp || event.key === Qt.Key_Home || event.key === Qt.Key_End) {
            wheel.stop()
            root.contentY = event.key === Qt.Key_Home ? top : event.key === Qt.Key_End ? bottom : Math.max(top, Math.min(bottom, root.contentY + (event.key === Qt.Key_PageDown ? 1 : -1) * root.height))
            event.accepted = true
        }
    }
    WheelSmoother { id: wheel; view: root }
}

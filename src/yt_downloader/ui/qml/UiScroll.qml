import QtQuick
import QtQuick.Controls.Basic

Flickable {
    id: root
    clip: true
    contentWidth: width
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    ScrollBar.vertical: ScrollBar {
        id: scrollbar
        width: 8
        policy: ScrollBar.AsNeeded
        onPressedChanged: if (pressed) wheel.stop()
        contentItem: Rectangle { implicitWidth: 5; radius: 3; color: theme.state.muted; opacity: scrollbar.pressed ? 0.8 : scrollbar.hovered ? 0.55 : 0.3 }
    }
    WheelSmoother { id: wheel; view: root }
}

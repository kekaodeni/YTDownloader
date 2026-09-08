import QtQuick
import QtQuick.Controls.Basic

Switch {
    id: control
    implicitHeight: 36
    implicitWidth: implicitContentWidth + 62
    font.family: theme.fontFamily("Body", text)
    font.pointSize: theme.fontSize("Body")
    font.weight: theme.fontWeight("Body")
    spacing: 12
    indicator: Rectangle {
        x: 0; y: (control.height - height) / 2
        width: 42; height: 24; radius: 12
        color: control.checked ? theme.state.accent : theme.state.stroke
        border.width: control.visualFocus ? 2 : 0
        border.color: theme.state.text
        Behavior on color { ColorAnimation { duration: shell.state.reduceMotion ? 0 : 120 } }
        Rectangle {
            width: 16; height: 16; radius: 8; y: 4
            x: control.checked ? 22 : 4
            color: control.checked ? theme.state.onAccent : theme.state.surface
            Behavior on x { SmoothedAnimation { duration: shell.state.reduceMotion ? 0 : 140; velocity: -1 } }
        }
    }
    contentItem: UiText { text: control.text; leftPadding: 54; color: control.enabled ? theme.state.text : theme.state.disabled }
}

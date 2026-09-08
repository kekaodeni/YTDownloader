import QtQuick
import QtQuick.Controls.Basic

MenuItem {
    id: control
    property bool destructive: false
    implicitHeight: 36
    leftPadding: 10
    rightPadding: 12
    spacing: 10
    font.family: theme.fontFamily("Body", text)
    font.pointSize: theme.fontSize("Body")
    font.weight: theme.fontWeight("Body")
    property bool pointerHovered: pointerHover.hovered
    HoverHandler { id: pointerHover }
    icon.width: 18
    icon.height: 18
    icon.color: !enabled ? theme.state.disabled : destructive ? theme.state.danger : theme.state.secondary
    property color foreground: !enabled ? theme.state.disabled : destructive ? theme.state.danger : theme.state.text
    palette.text: foreground
    palette.windowText: foreground
    palette.highlightedText: foreground
    Accessible.name: text
    background: Rectangle {
        radius: 6
        objectName: "menuHighlight-" + control.text
        color: theme.state.selection
        opacity: control.enabled && (control.highlighted || control.pointerHovered) ? 1 : 0
        border.width: control.visualFocus ? 1 : 0
        border.color: theme.state.accent
    }
}

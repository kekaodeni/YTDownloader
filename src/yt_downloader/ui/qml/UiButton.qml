import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control
    property string appearance: "normal"
    property bool selected: false
    property string hint: ""
    implicitHeight: 38
    implicitWidth: Math.max(38, implicitContentWidth + leftPadding + rightPadding)
    leftPadding: 14
    rightPadding: 14
    spacing: 8
    hoverEnabled: true
    font.family: theme.fontFamily("Button", text)
    font.pointSize: theme.fontSize("Button")
    font.weight: theme.fontWeight("Button")
    palette.buttonText: !enabled ? theme.state.disabled : appearance === "primary" ? theme.state.onAccent : appearance === "danger" ? theme.state.danger : selected ? theme.state.accent : theme.state.text
    icon.width: 20
    icon.height: 20
    icon.color: palette.buttonText
    Accessible.name: text || hint
    ToolTip.text: hint
    ToolTip.visible: hovered && hint.length > 0
    ToolTip.delay: 700
    scale: down && !shell.state.reduceMotion ? 0.985 : 1
    Behavior on scale { SmoothedAnimation { duration: 90; velocity: -1 } }
    background: Rectangle {
        radius: 8
        readonly property bool quiet: control.appearance === "quiet" || control.appearance === "nav"
        // Keep RGB opaque; animate coverage separately to avoid a black midpoint.
        opacity: quiet && control.enabled && !control.selected && !control.down && !control.hovered && !control.visualFocus ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: shell.state.reduceMotion ? 0 : 120 } }
        color: !control.enabled ? theme.state.subtle : control.appearance === "primary" ? (control.hovered ? theme.state.accentHover : theme.state.accent) : control.selected ? theme.state.selection : control.down ? theme.state.stroke : control.hovered ? theme.state.subtle : quiet ? theme.state.subtle : theme.state.surface
        border.width: control.visualFocus ? 2 : control.appearance === "normal" || control.appearance === "danger" ? 1 : 0
        border.color: control.visualFocus ? theme.state.accent : theme.state.stroke
        Behavior on color { ColorAnimation { duration: shell.state.reduceMotion ? 0 : 120 } }
    }
}

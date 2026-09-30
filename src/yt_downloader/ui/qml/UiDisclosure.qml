import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Button {
    id: control
    property string label: ""
    property bool expanded: false

    objectName: "advancedOptionsToggle"
    implicitHeight: 42
    implicitWidth: 260
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    font.family: theme.fontFamily("Button", label)
    font.pointSize: theme.fontSize("Button")
    font.weight: theme.fontWeight("Button")
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.description: expanded ? i18n.messages["download.advanced_expanded"] : i18n.messages["download.advanced_collapsed"]
    background: Rectangle {
        radius: 8
        color: !control.enabled ? theme.state.subtle
             : control.down ? theme.state.stroke
             : control.hovered ? theme.state.subtle
             : theme.state.surface
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? theme.state.accent : theme.state.stroke
        Behavior on color { ColorAnimation { duration: motion.micro } }
    }

    contentItem: RowLayout {
        spacing: 10
        Image {
            source: assetsBase + "icons/settings_regular.svg"
            sourceSize.width: 18
            sourceSize.height: 18
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            opacity: control.enabled ? 1 : 0.55
        }
        UiText {
            Layout.fillWidth: true
            text: control.label
            role: "Button"
            color: control.enabled ? theme.state.text : theme.state.disabled
            elide: Text.ElideRight
        }
        Image {
            source: assetsBase + (theme.state.dark ? "icons/chevron_down_dark.svg" : "icons/chevron_down_light.svg")
            sourceSize.width: 14
            sourceSize.height: 14
            Layout.preferredWidth: 14
            Layout.preferredHeight: 14
            rotation: control.expanded ? 0 : -90
            Behavior on rotation { NumberAnimation { duration: motion.reduced ? 0 : motion.fast } }
        }
    }
}

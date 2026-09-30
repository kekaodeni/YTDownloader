import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

UiButton {
    id: navButton
    property bool compact: false
    property bool secondary: false
    property string iconName: ""
    property bool filledIcon: false
    property color foreground: !enabled ? theme.state.disabled : selected ? theme.state.accent : theme.state.text
    Behavior on foreground { ColorAnimation { duration: motion.micro } }
    appearance: "nav"
    leftPadding: compact ? 14 : 12
    rightPadding: 12
    implicitHeight: secondary ? Math.max(46, label.implicitHeight + 20) : 44
    Accessible.role: Accessible.PageTab
    Accessible.selected: selected
    background: Rectangle {
        radius: 9
        color: navButton.down ? theme.state.stroke : theme.state.subtle
        opacity: (!navButton.selected && (navButton.hovered || navButton.down)) || navButton.visualFocus ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: motion.micro } }
        border.width: navButton.visualFocus ? 2 : 0
        border.color: theme.state.accent
    }
    contentItem: RowLayout {
        spacing: 10
        ToolButton {
            Layout.preferredWidth: 20; Layout.preferredHeight: 20
            padding: 0; enabled: false; Accessible.ignored: true
            icon.source: assetsBase + "icons/" + navButton.iconName + (navButton.selected && navButton.filledIcon ? "_filled.svg" : "_regular.svg")
            icon.width: 20; icon.height: 20; icon.color: navButton.foreground
            background: null
        }
        UiText {
            id: label
            Layout.fillWidth: true
            visible: !navButton.compact
            text: navButton.text
            font: navButton.font
            color: navButton.foreground
            wrapMode: navButton.secondary ? Text.Wrap : Text.NoWrap
            elide: navButton.secondary ? Text.ElideNone : Text.ElideRight
        }
    }
}

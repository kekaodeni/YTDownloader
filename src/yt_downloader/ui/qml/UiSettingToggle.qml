import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root
    property string label: ""
    property alias checked: toggle.checked
    signal changed(bool checked)

    implicitWidth: 280
    implicitHeight: Math.max(36, labelText.implicitHeight)
    spacing: 14

    UiText {
        id: labelText
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
        text: root.label
        wrapMode: Text.Wrap
    }
    UiSwitch {
        id: toggle
        text: ""
        Layout.preferredWidth: 62
        Layout.minimumWidth: 62
        Layout.maximumWidth: 62
        Layout.preferredHeight: 36
        Layout.alignment: Qt.AlignVCenter
        Accessible.name: root.label
        onToggled: root.changed(checked)
    }
}

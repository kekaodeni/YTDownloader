import QtQuick
import QtQuick.Layouts

Item {
    id: row
    default property alias controls: actions.data
    property string label: ""
    property string description: ""
    property real controlWidth: 240
    property bool separator: false
    readonly property real effectiveControlWidth: Math.min(width, Math.max(controlWidth, actions.implicitWidth))
    implicitHeight: Math.max(60, grid.implicitHeight + 20)
    GridLayout {
        id: grid
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        columns: row.width - row.effectiveControlWidth < 180 ? 1 : 2
        columnSpacing: 24; rowSpacing: 10
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            UiText { objectName: "settingRowLabel"; Layout.fillWidth: true; text: row.label; wrapMode: Text.Wrap }
            UiText { objectName: "settingRowDescription"; Layout.fillWidth: true; visible: text.length > 0; text: row.description; role: "Caption"; color: theme.state.secondary; wrapMode: Text.WrapAnywhere }
        }
        RowLayout {
            id: actions
            Layout.fillWidth: grid.columns === 1
            Layout.preferredWidth: row.effectiveControlWidth
            Layout.maximumWidth: grid.columns === 1 ? row.width : row.effectiveControlWidth
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            spacing: 8
        }
    }
    Rectangle { visible: row.separator; height: 1; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; color: theme.state.stroke; opacity: .45 }
}

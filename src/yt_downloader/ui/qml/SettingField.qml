import QtQuick
import QtQuick.Layouts
ColumnLayout {
    id: root
    property string label: ""
    property string description: ""
    default property alias editor: controls.data
    spacing: 8
    data: [
        UiText { Layout.fillWidth: true; text: root.label; role: "FormLabel"; visible: text.length > 0 },
        ColumnLayout { id: controls; Layout.fillWidth: true; spacing: 8 },
        UiText { Layout.fillWidth: true; text: root.description; role: "Caption"; color: theme.state.muted; wrapMode: Text.Wrap; visible: text.length > 0 }
    ]
}

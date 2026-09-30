import QtQuick
import QtQuick.Layouts

Rectangle {
    id: card
    default property alias contents: content.data
    property string title: ""
    color: theme.state.surface
    radius: 12
    border.color: theme.state.stroke
    implicitHeight: content.implicitHeight + 36
    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 18
        spacing: 8
        UiText { Layout.fillWidth: true; visible: card.title.length > 0; text: card.title; role: "SectionTitle"; wrapMode: Text.Wrap }
    }
}

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A result presentation, never a batch downloader or parent task.
Rectangle {
    id: root
    required property var item
    implicitHeight: content.implicitHeight + 32
    color: theme.state.surface
    radius: 12
    border.color: theme.state.stroke
    objectName: item.id
    ColumnLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: parent.top; anchors.margins: 16
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                UiText { Layout.fillWidth: true; text: i18n.messages["notification.batch_complete"]; role: "CardTitle"; wrapMode: Text.Wrap }
                UiText {
                    objectName: "batchCounts-" + root.item.id
                    Layout.fillWidth: true
                    text: i18n.messages["batch.completed"].replace("{count}", root.item.completed)
                          + (root.item.failed ? " · " + i18n.messages["batch.failed"].replace("{count}", root.item.failed) : "")
                    role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap
                }
                UiText { visible: root.item.cancelled > 0; text: i18n.messages["batch.cancelled"].replace("{count}", root.item.cancelled); role: "Caption"; color: theme.state.muted }
            }
        }
        Flow {
            Layout.fillWidth: true; spacing: 8
            UiButton {
                objectName: "batchDetails-" + root.item.id
                text: root.item.expanded ? i18n.messages["batch.hide_details"] : i18n.messages["batch.details"]
                onClicked: download.summaryAction(root.item.id, "details")
            }
            UiButton { text: i18n.messages["action.open_folder"]; onClicked: download.summaryAction(root.item.id, "folder") }
        }
        Item {
            id: details
            Layout.fillWidth: true
            Layout.preferredHeight: root.item.expanded ? rows.implicitHeight : 0
            clip: true
            opacity: root.item.expanded ? 1 : 0
            Behavior on Layout.preferredHeight { NumberAnimation { duration: motion.geometry; easing.type: motion.easing } }
            Behavior on opacity { NumberAnimation { duration: motion.standard; easing.type: motion.easing } }
            ColumnLayout {
                id: rows
                width: parent.width
                spacing: 8
                Repeater {
                    model: root.item.details
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 10
                        Thumbnail { Layout.preferredWidth: 52; Layout.preferredHeight: 30; source: modelData.thumbnail; placeholder: i18n.messages["thumbnail.video"] }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            UiText { Layout.fillWidth: true; text: modelData.title; role: "Secondary"; elide: Text.ElideRight }
                            UiText { Layout.fillWidth: true; text: modelData.quality + " · " + modelData.size; role: "Caption"; color: theme.state.muted; elide: Text.ElideRight }
                        }
                        UiText { text: i18n.messages[modelData.statusKey]; role: "Caption"; color: theme.state.secondary }
                    }
                }
            }
        }
    }
}

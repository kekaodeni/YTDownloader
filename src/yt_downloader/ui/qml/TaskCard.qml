import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root
    required property var item
    property bool exiting: false
    property real entranceOffset: 0
    transform: Translate { y: root.entranceOffset }
    objectName: "task-" + item.id
    implicitHeight: content.implicitHeight + 32
    height: implicitHeight
    color: theme.state.surface; radius: 12; border.color: theme.state.stroke
    enabled: !exiting
    ListView.onRemove: exiting = true
    ListView.onReused: { exiting = false; opacity = 1 }
    RowLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16
        spacing: 16
        Thumbnail { Layout.preferredWidth: 104; Layout.preferredHeight: 59; Layout.alignment: Qt.AlignTop; source: root.item.thumbnail; placeholder: i18n.messages["thumbnail.video"]; visible: root.width >= 570 }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 9
            RowLayout {
                Layout.fillWidth: true
                UiText { Layout.fillWidth: true; text: root.item.title; role: "CardTitle"; elide: Text.ElideRight }
                UiButton { width: 30; height: 30; appearance: "quiet"; icon.source: assetsBase + "icons/delete_regular.svg"; hint: i18n.messages["task.delete_hint"].replace("{title}", root.item.title); onClicked: download.taskAction(root.item.id, "remove") }
            }
            UiText { text: root.item.clipRange ? root.item.quality + " · " + i18n.messages["task.clip_range"].replace("{range}", root.item.clipRange) : root.item.quality; role: "Caption"; color: theme.state.muted; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                UiText {
                    objectName: "taskStatus-" + root.item.id
                    Layout.fillWidth: true
                    text: root.item.warningMessages && root.item.warningMessages.length
                          ? (i18n.messages[root.item.statusKey] || root.item.statusText) + " · " + root.item.warningMessages.map(function(message) { return i18n.sourceText(message) }).join(" · ")
                          : (i18n.messages[root.item.statusKey] || root.item.statusText)
                    role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap
                }
                UiText { text: root.item.percentText; role: "Numeric" }
            }
            UiProgress { Layout.fillWidth: true; value: root.item.percent / 100; indeterminate: root.item.indeterminate; immediate: root.item.stopping || root.item.open }
            Flow {
                Layout.fillWidth: true; spacing: 14
                UiText { text: root.item.speed; role: "Numeric"; color: theme.state.secondary }
                UiText { text: root.item.sizeTemplate ? i18n.messages[root.item.sizeTemplate].replace("{downloaded}", root.item.sizeDownloaded || "—").replace("{total}", root.item.sizeEstimated ? i18n.messages["task.estimate"].replace("{size}", root.item.sizeTotal || "—") : (root.item.sizeTotal || "—")) : root.item.size; role: "Numeric"; color: theme.state.secondary }
                UiText { text: root.item.etaTemplate ? i18n.messages[root.item.etaTemplate].replace("{time}", root.item.etaTime || "—") : root.item.eta; role: "Numeric"; color: theme.state.secondary }
            }
            Flow {
                Layout.fillWidth: true; spacing: 8
                UiButton { objectName: "taskPause-" + root.item.id; text: root.item.resumeEnabled ? i18n.messages["task.action.resume"] : i18n.messages["task.action.pause"]; appearance: "normal"; visible: root.item.pauseVisible; enabled: root.item.pauseEnabled || root.item.resumeEnabled; onClicked: download.taskAction(root.item.id, root.item.resumeEnabled ? "resume" : "pause") }
                UiButton { objectName: "taskCancel-" + root.item.id; text: root.item.status === "CANCELLING" ? i18n.messages["task.status.cancelling"] : i18n.messages["task.action.cancel"]; appearance: "normal"; visible: root.item.cancel; enabled: root.item.cancelEnabled; onClicked: download.taskAction(root.item.id, "cancel") }
                UiButton { text: i18n.messages["action.retry"]; visible: root.item.retry; enabled: !download.state.busy; onClicked: download.taskAction(root.item.id, "retry") }
                UiButton { text: i18n.messages["action.open_file"]; visible: root.item.open; onClicked: download.taskAction(root.item.id, "open") }
                UiButton { text: i18n.messages["action.open_folder"]; visible: root.item.folder; onClicked: download.taskAction(root.item.id, "folder") }
            }
        }
    }
}

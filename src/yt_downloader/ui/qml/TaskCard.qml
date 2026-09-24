import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root
    required property var item
    property bool exiting: false
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
        Thumbnail { Layout.preferredWidth: 104; Layout.preferredHeight: 59; Layout.alignment: Qt.AlignTop; source: root.item.thumbnail; placeholder: "视频"; visible: root.width >= 570 }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 9
            RowLayout {
                Layout.fillWidth: true
                UiText { Layout.fillWidth: true; text: root.item.title; role: "CardTitle"; elide: Text.ElideRight }
                UiButton { width: 30; height: 30; appearance: "quiet"; icon.source: assetsBase + "icons/delete_regular.svg"; hint: "删除任务 " + root.item.title; onClicked: download.taskAction(root.item.id, "remove") }
            }
            UiText { text: root.item.quality; role: "Caption"; color: theme.state.muted }
            RowLayout {
                Layout.fillWidth: true
                UiText { Layout.fillWidth: true; text: root.item.statusText; role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiText { text: root.item.percentText; role: "Numeric" }
            }
            UiProgress { Layout.fillWidth: true; value: root.item.percent / 100; indeterminate: root.item.indeterminate; immediate: root.item.stopping || root.item.open }
            Flow {
                Layout.fillWidth: true; spacing: 14
                UiText { text: root.item.speed; role: "Numeric"; color: theme.state.secondary }
                UiText { text: root.item.size; role: "Numeric"; color: theme.state.secondary }
                UiText { text: root.item.eta; role: "Numeric"; color: theme.state.secondary }
            }
            Flow {
                Layout.fillWidth: true; spacing: 8
                UiButton { objectName: "taskPause-" + root.item.id; text: root.item.pauseText; appearance: "normal"; visible: root.item.pauseVisible; enabled: root.item.pauseEnabled || root.item.resumeEnabled; onClicked: download.taskAction(root.item.id, root.item.resumeEnabled ? "resume" : "pause") }
                UiButton { objectName: "taskCancel-" + root.item.id; text: root.item.cancelText; appearance: "normal"; visible: root.item.cancel; enabled: root.item.cancelEnabled; onClicked: download.taskAction(root.item.id, "cancel") }
                UiButton { text: "重试"; visible: root.item.retry; enabled: !download.state.busy; onClicked: download.taskAction(root.item.id, "retry") }
                UiButton { text: "打开文件"; visible: root.item.open; onClicked: download.taskAction(root.item.id, "open") }
                UiButton { text: "打开文件夹"; visible: root.item.folder; onClicked: download.taskAction(root.item.id, "folder") }
            }
        }
    }
}

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQml.Models

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    width: 1200; height: 800; minimumWidth: 500; minimumHeight: 560
    visible: false
    title: "YT Downloader"
    font.family: theme.fontFamily("Body", "中文")
    font.pointSize: theme.fontSize("Body")
    font.weight: theme.fontWeight("Body")
    color: theme.state.canvas
    palette.window: theme.state.canvas
    palette.base: theme.state.surface
    palette.text: theme.state.text
    palette.windowText: theme.state.text
    palette.buttonText: theme.state.text
    palette.button: theme.state.surface
    palette.highlight: theme.state.selection
    palette.highlightedText: theme.state.text
    onClosing: function(event) { if (!shell.state.allowClose) { event.accepted = false; shell.requestClose() } }
    readonly property bool compact: width < 900
    FileDialog { id: cookiePicker; title: "选择 Netscape cookies.txt"; fileMode: FileDialog.OpenFile; nameFilters: ["Cookie 文件 (*.txt)", "所有文件 (*)"]; onAccepted: cookies.fileSelected(selectedFile.toString()) }
    Connections { target: cookies; function onPick_requested() { cookiePicker.open() } }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            id: nav
            Layout.preferredWidth: window.compact ? 72 : 206
            Layout.fillHeight: true
            color: theme.state.sidebar
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: theme.state.stroke }
            Column {
                id: branding; x: 16; y: 28; spacing: 12
                Image { width: 36; height: 36; source: assetsBase + "app-icon.png"; sourceSize.width: 72; sourceSize.height: 72 }
                UiText { text: "YT Downloader"; font.weight: Font.DemiBold; visible: !window.compact }
                UiText { text: "视频下载"; role: "Caption"; color: theme.state.muted; visible: !window.compact }
            }
            Item {
                id: navigation
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: branding.bottom
                anchors.leftMargin: 10; anchors.rightMargin: 10; anchors.topMargin: 30
                height: 4 * 49
                Rectangle {
                    width: parent.width; height: 44; radius: 9; color: theme.state.selection
                    y: shell.state.page * 49
                    Behavior on y { SmoothedAnimation { duration: shell.state.reduceMotion ? 0 : 220; velocity: -1 } }
                    Rectangle { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 18; radius: 2; color: theme.state.accent }
                }
                Column {
                    width: parent.width; spacing: 5
                    Repeater {
                        model: [{label:"下载", icon:"arrow_download"}, {label:"历史记录", icon:"history"}, {label:"设置", icon:"settings"}, {label:"关于", icon:"info"}]
                        UiButton {
                            required property var modelData
                            required property int index
                            objectName: "nav-" + index
                            implicitWidth: navigation.width; width: navigation.width; height: 44
                            text: window.compact ? "" : modelData.label
                            hint: modelData.label
                            appearance: "nav"; selected: shell.state.page === index
                            icon.source: assetsBase + "icons/" + modelData.icon + (selected ? "_filled.svg" : "_regular.svg")
                            leftPadding: window.compact ? 14 : 12
                            rightPadding: window.compact ? 14 : Math.max(12, width - implicitContentWidth - 12)
                            background: Rectangle { radius: 9; color: parent.hovered && !parent.selected ? theme.state.subtle : "transparent"; border.width: parent.visualFocus ? 2 : 0; border.color: theme.state.accent }
                            onClicked: shell._select_page(index)
                        }
                    }
                }
            }
            UiText { anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 20; text: "v" + shell.state.version; role: "Caption"; color: theme.state.muted; visible: !window.compact }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Rectangle {
                Layout.fillWidth: true; implicitHeight: notice.implicitHeight + 16
                visible: shell.state.updateVisible; color: theme.state.selection
                RowLayout { id: notice; anchors.fill: parent; anchors.margins: 8
                    UiText { Layout.fillWidth: true; text: shell.state.updateText; role: "Caption"; wrapMode: Text.Wrap }
                    UiButton { text: "查看更新"; appearance: "quiet"; onClicked: shell.show_update_requested() }
                    UiButton { text: "关闭"; appearance: "quiet"; onClicked: shell.hideUpdate() }
                }
            }
            Item {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                PageHost { anchors.fill: parent; objectName: "pageHost-" + pageIndex; property int pageIndex: 0; current: shell.state.page === 0; DownloadView { anchors.fill: parent } }
                PageHost { anchors.fill: parent; objectName: "pageHost-" + pageIndex; property int pageIndex: 1; current: shell.state.page === 1; HistoryView { anchors.fill: parent } }
                PageHost { anchors.fill: parent; objectName: "pageHost-" + pageIndex; property int pageIndex: 2; current: shell.state.page === 2; SettingsView { anchors.fill: parent } }
                PageHost { anchors.fill: parent; objectName: "pageHost-" + pageIndex; property int pageIndex: 3; current: shell.state.page === 3; AboutView { anchors.fill: parent } }
            }
        }
    }
    Instantiator {
        model: dialogs.model
        delegate: DialogView { required property var item; session: item.session; parent: window.Overlay.overlay }
    }
    FolderDialog {
        id: folder
        property string requestKey: ""
        title: "选择目录"
        onAccepted: dialogs.directorySelected(requestKey, selectedFolder.toString())
        onRejected: dialogs.directorySelected(requestKey, "")
    }
    Connections { target: dialogs; function onDirectory_requested(key, current) { folder.requestKey = key; folder.currentFolder = current; folder.open() } }
}

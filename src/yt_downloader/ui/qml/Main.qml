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
    font.family: theme.fontFamily("Body", i18n.messages["nav.download"])
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
    FileDialog { id: cookiePicker; objectName: "cookiePicker"; title: i18n.messages["cookie.picker_title"]; fileMode: FileDialog.OpenFile; nameFilters: [i18n.messages["cookie.file_filter"], i18n.messages["common.all_files_filter"]]; onAccepted: cookies.fileSelected(selectedFile.toString()) }
    RowLayout {
        visible: !shell.state.recoveryVisible
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
                UiText { text: i18n.messages["app.subtitle"]; role: "Caption"; color: theme.state.muted; visible: !window.compact }
            }
            Item {
                id: navigation
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: branding.bottom
                anchors.leftMargin: 10; anchors.rightMargin: 10; anchors.topMargin: 30
                height: 4 * 49
                Rectangle {
                    width: parent.width; height: 44; radius: 9; color: theme.state.selection
                    y: shell.state.page * 49
                    Behavior on y { SmoothedAnimation { duration: motion.reduced ? 0 : motion.page; velocity: -1 } }
                    Rectangle { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 18; radius: 2; color: theme.state.accent }
                }
                Column {
                    width: parent.width; spacing: 5
                    Repeater {
                        model: [{key:"nav.download", icon:"arrow_download"}, {key:"nav.history", icon:"history"}, {key:"nav.settings", icon:"settings"}, {key:"nav.about", icon:"info"}]
                        UiButton {
                            required property var modelData
                            required property int index
                            objectName: "nav-" + index
                            implicitWidth: navigation.width; width: navigation.width; height: 44
                            text: window.compact ? "" : i18n.messages[modelData.key]
                            hint: i18n.messages[modelData.key]
                            appearance: "nav"; selected: shell.state.page === index
                            icon.source: assetsBase + "icons/" + modelData.icon + (selected ? "_filled.svg" : "_regular.svg")
                            leftPadding: window.compact ? 14 : 12
                            // Leave room for fractional-DPI text rasterization.
                            rightPadding: window.compact ? 14 : Math.max(12, width - Math.ceil(implicitContentWidth) - 14)
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
                    UiButton { text: i18n.messages["common.view_update"]; appearance: "quiet"; onClicked: shell.show_update_requested() }
                    UiButton { text: i18n.messages["common.close"]; appearance: "quiet"; onClicked: shell.hideUpdate() }
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
    ColumnLayout {
        visible: shell.state.recoveryVisible
        anchors.centerIn: parent; width: Math.min(parent.width - 64, 540); spacing: 24
        UiText { Layout.fillWidth: true; text: shell.state.recoveryText; role: "SectionTitle"; wrapMode: Text.Wrap }
        UiText { Layout.fillWidth: true; text: shell.state.recoveryBusy ? i18n.messages["recovery.update_in_progress"] : i18n.messages["recovery.files_retained"]; role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap }
        UiProgress { Layout.fillWidth: true; indeterminate: true; visible: shell.state.recoveryBusy }
        UiButton { text: i18n.messages["common.view_details"]; visible: !shell.state.recoveryBusy; onClicked: shell.recovery_details_requested() }
    }
    Instantiator {
        model: dialogs.model
        delegate: DialogView { required property var item; session: item.session; parent: window.Overlay.overlay }
    }
    FolderDialog {
        id: folder
        property string requestKey: ""
        title: i18n.messages["dialog.choose_directory"]
        onAccepted: dialogs.directorySelected(requestKey, selectedFolder.toString())
        onRejected: dialogs.directorySelected(requestKey, "")
    }
    Connections { target: dialogs; function onDirectory_requested(key, current) { folder.requestKey = key; folder.currentFolder = current; folder.open() } }
}

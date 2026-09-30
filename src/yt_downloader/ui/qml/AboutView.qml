import QtQuick
import QtQuick.Layouts
Item {
    id: root; objectName: "aboutPage"
    UiScroll {
        id: aboutScroll
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32
        contentHeight: content.implicitHeight
        ColumnLayout {
            id: content; width: aboutScroll.width - aboutScroll.contentInsetRight; spacing: 24
            UiText { text: i18n.messages["nav.about"]; role: "PageTitle" }
            Item { Layout.preferredHeight: 20 }
            Image { source: assetsBase + "app-icon.png"; Layout.preferredWidth: 72; Layout.preferredHeight: 72; sourceSize.width: 144; sourceSize.height: 144 }
            ColumnLayout { Layout.fillWidth: true; spacing: 8
                UiText { text: "YT Downloader"; role: "PageTitle"; font.pointSize: 23 }
                UiText { text: i18n.messages["about.version"].replace("{version}", shell.state.version); role: "Secondary"; color: theme.state.secondary }
                Flow { Layout.fillWidth: true; spacing: 8
                    UiButton { objectName: "aboutUpdateAction"; text: shell.state.updateChecking ? i18n.messages["update.checking"] : shell.state.updateAction; enabled: !shell.state.updateChecking; onClicked: shell.updateAction() }
                }
                UiText { Layout.fillWidth: true; text: shell.state.updateStatus; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
            }
            UiText { Layout.fillWidth: true; text: i18n.messages["about.description"]; color: theme.state.secondary; wrapMode: Text.Wrap }
            Flow { Layout.fillWidth: true; spacing: 8
                UiButton { text: i18n.messages["about.project"]; onClicked: shell.openProject() }
                UiButton { text: i18n.messages["about.copy_address"]; visible: shell.state.projectError.length > 0; onClicked: shell.copyProject() }
            }
            UiText { Layout.fillWidth: true; text: shell.state.projectError; visible: text.length > 0; role: "Caption"; wrapMode: Text.WrapAnywhere }
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
            UiText { Layout.fillWidth: true; text: i18n.messages["about.disclaimer"]; role: "Caption"; color: theme.state.muted; wrapMode: Text.Wrap }
        }
    }
}

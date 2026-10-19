import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: guide
    required property var session
    property bool detailsOpen: false
    readonly property string browser: session.state.browser
    readonly property var info: browserCompanion.state.rows[["chrome", "edge", "firefox"].indexOf(browser)]
    Layout.fillWidth: true
    spacing: 16
    SettingCard {
        objectName: "guideStepConnection"
        Layout.fillWidth: true; title: i18n.messages["browser.step_connection"]
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.guide_connect"]; wrapMode: Text.Wrap }
    }
    SettingCard {
        objectName: "guideStepInstall"
        Layout.fillWidth: true; title: i18n.messages["browser.step_install"]
        UiText { objectName: "guide-browser-instructions"; Layout.fillWidth: true; text: i18n.messages["browser.install_" + guide.browser]; wrapMode: Text.Wrap }
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.portable_path"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
        TextArea {
            objectName: "guideExtensionPath"
            Layout.fillWidth: true
            text: guide.info.folderPath
            readOnly: true; selectByMouse: true; persistentSelection: true
            wrapMode: TextEdit.WrapAnywhere; textFormat: TextEdit.PlainText
            padding: 10
            color: theme.state.secondary; selectionColor: theme.state.selection; selectedTextColor: theme.state.text
            font.family: theme.fontFamily("Caption", text); font.pointSize: theme.fontSize("Caption")
            Accessible.name: i18n.messages["browser.portable_path"]
            background: Rectangle { radius: 6; color: theme.state.subtle }
        }
    }
    SettingCard {
        objectName: "guideStepSend"
        Layout.fillWidth: true; title: i18n.messages["browser.step_send"]
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.send_help"]; wrapMode: Text.Wrap }
    }
    UiDisclosure { objectName: "guideMore"; Layout.fillWidth: true; label: i18n.messages["browser.guide_more"]; expanded: guide.detailsOpen; onClicked: guide.detailsOpen = !guide.detailsOpen }
    SettingCard {
        objectName: "guideDetails"
        Layout.fillWidth: true; visible: guide.detailsOpen
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.guide_native"]; wrapMode: Text.Wrap; color: theme.state.secondary }
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.guide_troubleshoot"]; wrapMode: Text.Wrap }
        UiText { objectName: "guideLastLine"; Layout.fillWidth: true; text: i18n.messages["browser.guide_movement"]; wrapMode: Text.Wrap }
    }
}

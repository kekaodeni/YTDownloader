import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: guide
    required property var session
    readonly property string browser: session.state.browser
    readonly property var info: browserCompanion.state.rows[["chrome", "edge", "firefox"].indexOf(browser)]
    Layout.fillWidth: true
    spacing: 16
    Flow {
        Layout.fillWidth: true; spacing: 8
        Repeater {
            model: ["chrome", "edge", "firefox"]
            delegate: UiButton {
                required property string modelData
                objectName: "guide-browser-" + modelData
                text: modelData === "edge" ? "Microsoft Edge" : modelData === "chrome" ? "Chrome" : "Firefox"
                selected: guide.browser === modelData
                onClicked: guide.session.selectBrowser(modelData)
            }
        }
    }
    SettingCard {
        Layout.fillWidth: true; title: i18n.messages["browser.step_connection"]
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.guide_connect"]; wrapMode: Text.Wrap }
    }
    SettingCard {
        Layout.fillWidth: true; title: i18n.messages["browser.step_install"]
        UiText { objectName: "guide-browser-instructions"; Layout.fillWidth: true; text: i18n.messages["browser.install_" + guide.browser]; wrapMode: Text.Wrap }
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.portable_path"] + "\n" + guide.info.folderPath; role: "Caption"; wrapMode: Text.WrapAnywhere; color: theme.state.secondary }
    }
    SettingCard {
        Layout.fillWidth: true; title: i18n.messages["browser.step_send"]
        UiText { Layout.fillWidth: true; text: i18n.messages["browser.send_help"]; wrapMode: Text.Wrap }
    }
    UiText { Layout.fillWidth: true; text: i18n.messages["browser.guide_native"]; wrapMode: Text.Wrap; color: theme.state.secondary }
    UiText { Layout.fillWidth: true; text: i18n.messages["browser.guide_troubleshoot"]; wrapMode: Text.Wrap }
    UiText { Layout.fillWidth: true; text: i18n.messages["browser.guide_movement"]; wrapMode: Text.Wrap }
    UiText { Layout.fillWidth: true; text: i18n.messages["browser.privacy"]; wrapMode: Text.Wrap; color: theme.state.secondary; role: "Caption" }
}

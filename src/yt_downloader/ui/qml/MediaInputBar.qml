import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property var controller
    property string itemPrefix: ""
    readonly property bool locked: controller.state.toolBusy === true
    Layout.fillWidth: true
    spacing: 12
        GridLayout {
            Layout.fillWidth: true; columnSpacing: 10; rowSpacing: 10
            columns: root.width < 360 ? 1 : 2
            UiField {
                id: urlField; objectName: root.itemPrefix + "urlInput"
                Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 46
                placeholderText: i18n.messages["download.url_placeholder"]
                text: controller.state.url
                enabled: !controller.state.busy && !root.locked
                Accessible.name: i18n.messages["download.url_placeholder"]
                onTextChanged: controller.setField("url", text)
                onAccepted: controller.requestParse()
                rightPadding: clearUrl.visible ? 40 : 12
                UiButton { id: clearUrl; objectName: root.itemPrefix + "clearUrl"; width: 32; height: 32; anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; visible: urlField.text.length > 0; text: "×"; hint: i18n.messages["download.link_clear"]; appearance: "quiet"; onClicked: controller.setField("url", "") }
            }
            UiButton {
                objectName: root.itemPrefix + "parseButton"
                text: controller.state.parseText; appearance: "primary"; implicitHeight: 46
                enabled: !controller.state.cancelling && !root.locked
                onClicked: controller.requestParse()
            }
        }
        UiText { Layout.fillWidth: true; visible: controller.state.clipboardHint.length > 0 && !controller.state.busy && !root.locked; text: controller.state.clipboardHint; role: "Caption"; color: theme.state.muted; elide: Text.ElideRight }
        GridLayout {
            Layout.fillWidth: true; columnSpacing: 8; rowSpacing: 8
            columns: root.width < 500 ? 1 : root.width < 760 ? 2 : 6
            UiText { text: i18n.messages["download.login_status"]; role: "Caption" }
            UiText {
                objectName: root.itemPrefix + "cookieAuthStatus"
                visible: text.length > 0
                text: controller.state.cookieAuthStatus
                role: "Caption"
                Layout.fillWidth: true; wrapMode: Text.Wrap
                color: controller.state.cookieAuthSeverity === "success" ? theme.state.success : controller.state.cookieAuthSeverity === "error" ? theme.state.accent : theme.state.secondary
            }
            Item { Layout.fillWidth: true; visible: root.width >= 760 }
            UiSwitch { objectName: root.itemPrefix + "useCookieSwitch"; text: i18n.messages["download.use_cookie"]; enabled: !controller.state.busy && !root.locked; checked: controller.state.cookieEnabled; onToggled: controller.setCookieEnabled(checked) }
            UiButton { objectName: root.itemPrefix + "cookieManagementButton"; text: i18n.messages["download.manage_cookie"]; appearance: "normal"; enabled: !controller.state.busy && !root.locked; onClicked: shell.openCookieSettings() }
            UiButton { objectName: root.itemPrefix + "cookieRetry"; text: i18n.messages["download.reparse"]; visible: controller.state.cookieAuthInvalid; enabled: !controller.state.busy && !root.locked; onClicked: controller.requestParse() }
        }
        UiText {
            objectName: root.itemPrefix + "cookieAuthWarning"
            Layout.fillWidth: true
            visible: controller.state.cookieAuthWarning.length > 0 || controller.state.cookieHint.length > 0
            text: controller.state.cookieAuthWarning.length > 0 ? controller.state.cookieAuthWarning : controller.state.cookieHint
            role: "Caption"
            color: controller.state.cookieAuthInvalid || controller.state.cookieAuthWarning.length > 0 ? theme.state.accent : theme.state.secondary
            wrapMode: Text.Wrap
        }
        ColumnLayout {
            Layout.fillWidth: true; visible: controller.state.busy; spacing: 8
            UiProgress { Layout.fillWidth: true; indeterminate: true }
            UiText { Layout.fillWidth: true; text: controller.state.parseHint || (controller.state.cancelling ? i18n.messages["download.stop_parsing"] : i18n.messages["download.fetching_info"]); color: theme.state.secondary; role: "Caption"; wrapMode: Text.Wrap }
        }
}

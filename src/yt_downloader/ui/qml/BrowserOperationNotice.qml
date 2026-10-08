import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property var info
    required property var areas
    readonly property bool active: areas.indexOf(info.noticeArea) >= 0
    spacing: 6
    UiText {
        objectName: "browser-notice-" + root.areas[0] + "-" + root.info.browser
        Layout.fillWidth: true
        Layout.minimumHeight: 42
        text: root.active && root.info.noticeKey ? i18n.messages[root.info.noticeKey] : ""
        wrapMode: Text.Wrap
        color: root.info.noticeError ? theme.state.danger : theme.state.secondary
        Accessible.role: Accessible.StaticText
    }
    UiProgress {
        Layout.fillWidth: true
        Layout.preferredHeight: 4
        opacity: root.active && root.info.busy ? 1 : 0
        indeterminate: root.active && root.info.busy
    }
}

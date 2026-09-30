import QtQuick

Rectangle {
    id: root
    property real value: 0
    property bool indeterminate: false
    property bool immediate: false
    property real visualValue: value
    implicitHeight: 5
    radius: height / 2
    color: theme.state.subtle
    clip: true
    Accessible.role: Accessible.ProgressBar
    Accessible.name: i18n.messages["ui.download_progress"]
    Accessible.description: indeterminate ? i18n.messages["ui.processing"] : Math.round(value * 100) + "%"
    Behavior on visualValue { SmoothedAnimation { duration: root.immediate || motion.reduced ? 0 : motion.micro; velocity: -1 } }
    Rectangle {
        id: bar
        width: root.width * (root.indeterminate ? 0.25 : Math.max(0, Math.min(1, root.visualValue)))
        height: parent.height; radius: height / 2; color: theme.state.accent
        x: root.indeterminate ? (motion.reduced ? (root.width - width) / 2 : (root.width + width) * scan.value - width) : 0
    }
    QtObject { id: scan; property real value: 0 }
    NumberAnimation { target: scan; property: "value"; from: 0; to: 1; duration: 1250; loops: Animation.Infinite; running: root.indeterminate && root.visible && !motion.reduced }
}

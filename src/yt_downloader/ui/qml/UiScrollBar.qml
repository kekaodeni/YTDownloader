import QtQuick
import QtQuick.Controls.Basic

ScrollBar {
    id: bar
    property bool compact: false
    property bool recentActivity: false
    readonly property int edgeInset: compact ? 2 : 4
    property real restingThumbWidth: hovered ? (compact ? 5 : 6) : (compact ? 3 : 4)
    readonly property real thumbWidth: pressed ? (compact ? 6 : 7) : restingThumbWidth
    readonly property bool emphasized: active || hovered || pressed || recentActivity
    property real restingThumbOpacity: hovered ? 0.65 : emphasized ? 0.5 : 0.28
    property real restingTrackOpacity: hovered ? 0.055 : 0
    objectName: "uiScrollBar"
    orientation: Qt.Vertical
    hoverEnabled: true
    interactive: true
    policy: ScrollBar.AsNeeded
    implicitWidth: 12; width: 12
    topPadding: 4; bottomPadding: 4
    x: parent ? parent.width - width - edgeInset : 0
    y: 0
    height: parent ? parent.height : 0
    visible: size < 1 && height > 0
    minimumSize: Math.min(1, 36 / Math.max(1, availableHeight))
    // Pressed values bypass hover animations already in flight.
    Behavior on restingThumbWidth { enabled: !motion.reduced; NumberAnimation { duration: bar.hovered ? motion.micro : motion.standard; easing.type: motion.easing } }
    Behavior on restingThumbOpacity { NumberAnimation { duration: motion.reduced ? motion.micro : bar.hovered ? motion.micro : motion.standard; easing.type: motion.easing } }
    Behavior on restingTrackOpacity { NumberAnimation { duration: motion.micro } }
    // WheelSmoother animates contentY without Flickable.moving becoming true.
    // Native attached position changes cover wheel, touchpad and keyboard alike.
    onPositionChanged: {
        if (visible) {
            recentActivity = true
            if (!active && !pressed) linger.restart()
        }
    }
    onActiveChanged: {
        if (active) { recentActivity = true; linger.stop() }
        else if (recentActivity) linger.restart()
    }
    onPressedChanged: {
        if (pressed) { recentActivity = true; linger.stop() }
        else if (recentActivity) linger.restart()
    }
    SequentialAnimation {
        id: linger
        PauseAnimation { duration: 800 }
        ScriptAction { script: bar.recentActivity = false }
    }
    background: Item {
        Rectangle {
            anchors.centerIn: parent
            width: 8; height: Math.max(0, parent.height - 8); radius: width / 2
            color: theme.state.secondary
            opacity: bar.pressed ? 0.1 : bar.restingTrackOpacity
        }
    }
    contentItem: Item {
        Rectangle {
            objectName: "scrollThumb"
            anchors.horizontalCenter: parent.horizontalCenter
            width: bar.thumbWidth; height: parent.height; radius: width / 2
            color: theme.state.secondary
            opacity: bar.pressed ? 0.85 : bar.restingThumbOpacity
        }
    }
}

import QtQuick
Item {
    id: root
    property bool current: false
    visible: current || opacity > 0.001
    enabled: current
    opacity: current ? 1 : 0
    z: current ? 1 : 0
    Rectangle { anchors.fill: parent; color: theme.state.canvas; z: -1 }
    transform: Translate {
        y: root.current || shell.state.reduceMotion ? 0 : 8
        Behavior on y { SmoothedAnimation { duration: shell.state.reduceMotion ? 0 : 220; velocity: -1 } }
    }
    Behavior on opacity { NumberAnimation { duration: shell.state.reduceMotion ? 0 : 220; easing.type: Easing.OutCubic } }
}

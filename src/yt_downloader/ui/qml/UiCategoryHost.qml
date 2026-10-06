import QtQuick

Item {
    id: root
    property bool current: false
    property int index: 0
    property int selectedIndex: 0
    property color backgroundColor: theme.state.canvas
    property real visualOffset: current ? 0 : (index < selectedIndex ? -motion.categoryOffset : motion.categoryOffset)
    Behavior on visualOffset { NumberAnimation { duration: motion.movement; easing.type: motion.easing } }
    opacity: current ? 1 : 0
    visible: current || opacity > 0.001
    enabled: current
    z: current ? 1 : 0
    Rectangle { anchors.fill: parent; color: root.backgroundColor; z: -1 }
    transform: Translate {
        x: root.visualOffset
    }
    Behavior on opacity { NumberAnimation { duration: motion.standard; easing.type: motion.easing } }
}

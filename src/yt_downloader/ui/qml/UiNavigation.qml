import QtQuick

FocusScope {
    id: root
    property var model: []
    property int currentIndex: 0
    property bool compact: false
    property bool secondary: false
    property string itemPrefix: "nav-"
    readonly property int count: items.count
    readonly property var selectedItem: items.count > currentIndex ? items.itemAt(currentIndex) : null
    signal activated(int index)
    activeFocusOnTab: true
    implicitHeight: column.implicitHeight
    Keys.onUpPressed: activated((currentIndex + count - 1) % count)
    Keys.onDownPressed: activated((currentIndex + 1) % count)
    Rectangle {
        objectName: root.objectName + "-selection"
        width: root.width
        height: root.selectedItem ? root.selectedItem.height : 44
        y: root.selectedItem ? root.selectedItem.y : 0
        radius: 9; color: theme.state.selection; border.width: 0
        Behavior on y { SmoothedAnimation { duration: motion.reduced ? 0 : motion.page; velocity: -1 } }
        Behavior on height { SmoothedAnimation { duration: motion.reduced ? 0 : motion.page; velocity: -1 } }
        Rectangle { width: 3; height: 18; radius: 2; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; color: theme.state.accent }
    }
    Column {
        id: column
        width: parent.width; spacing: root.secondary ? 4 : 5
        Repeater {
            id: items
            model: root.model
            UiNavItem {
                required property var modelData
                required property int index
                objectName: root.itemPrefix + index
                width: column.width
                compact: root.compact; secondary: root.secondary
                text: i18n.messages[modelData.key]; hint: text
                selected: root.currentIndex === index
                iconName: modelData.icon; filledIcon: modelData.filled || false
                onClicked: { root.forceActiveFocus(Qt.MouseFocusReason); root.activated(index) }
            }
        }
    }
}

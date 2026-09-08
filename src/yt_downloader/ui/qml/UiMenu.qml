import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

Menu {
    id: control
    popupType: Popup.Item
    modal: true
    dim: false
    margins: 12
    padding: 6
    spacing: 2
    implicitWidth: 224
    font.family: theme.fontFamily("Body", "菜单")
    font.pointSize: theme.fontSize("Body")
    font.weight: theme.fontWeight("Body")
    palette.window: theme.state.elevated
    palette.text: theme.state.text
    palette.windowText: theme.state.text
    palette.highlight: theme.state.selection
    palette.highlightedText: theme.state.text
    transformOrigin: Item.TopLeft
    background: Rectangle {
        id: surface
        radius: 12
        color: theme.state.elevated
        border.color: theme.state.stroke
        RectangularShadow {
            anchors.fill: parent
            z: -1
            radius: surface.radius
            blur: 18
            spread: 0
            offset.y: 5
            color: theme.state.dark ? "#50000000" : "#200E1B30"
        }
    }
    contentItem: ListView {
        implicitHeight: contentHeight
        model: control.contentModel
        currentIndex: control.currentIndex
        spacing: control.spacing
        clip: true
        interactive: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds
        ScrollIndicator.vertical: ScrollIndicator { }
    }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: shell.state.reduceMotion ? 0 : 180; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: shell.state.reduceMotion ? 0 : 180; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: shell.state.reduceMotion ? 0 : 140 } }
}

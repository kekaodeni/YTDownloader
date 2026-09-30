import QtQuick
import QtQuick.Controls.Basic

ComboBox {
    id: control
    implicitHeight: 40
    implicitWidth: 200
    leftPadding: 12
    rightPadding: 34
    font.family: theme.fontFamily("Body", displayText)
    font.pointSize: theme.fontSize("Body")
    font.weight: theme.fontWeight("Body")
    Accessible.name: control.accessibleName
    property string accessibleName: i18n.messages["ui.select_option"]
    property bool subtleOverscroll: false
    Keys.onPressed: function(event) {
        if (popup.visible && (event.text.length > 0 || [Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown].indexOf(event.key) >= 0)) {
            Qt.callLater(function() { if (control.popup.visible) options.positionViewAtIndex(control.highlightedIndex, ListView.Contain) })
        }
        event.accepted = false
    }
    contentItem: UiText {
        text: control.displayText
        color: control.enabled ? theme.state.text : theme.state.disabled
        elide: Text.ElideRight
    }
    indicator: Image {
        width: 16; height: 16
        x: control.width - 27; y: (control.height - height) / 2
        source: assetsBase + "icons/chevron_down_" + (theme.state.dark ? "dark" : "light") + ".svg"
    }
    background: Rectangle {
        radius: 8; color: control.enabled ? theme.state.surface : theme.state.subtle
        border.color: control.visualFocus ? theme.state.accent : theme.state.stroke
        border.width: control.visualFocus ? 2 : 1
        Behavior on border.color { ColorAnimation { duration: motion.micro } }
    }
    delegate: ItemDelegate {
        // Native ComboBox connects AbstractButton.hoveredChanged to a
        // positionViewAtIndex call. Keep pointer feedback separate so a
        // partially visible row cannot scroll the popup just by hovering.
        hoverEnabled: false
        HoverHandler { id: optionHover }
        objectName: control.objectName + "-option-" + index
        width: options.width - 16; height: 38
        highlighted: control.highlightedIndex === index
        contentItem: UiText { text: modelData; elide: Text.ElideRight }
        background: Rectangle { radius: 6; color: parent.highlighted ? theme.state.selection : optionHover.hovered ? theme.state.subtle : "transparent" }
    }
    popup: Popup {
        objectName: "popup-" + control.objectName
        y: control.height + 5
        width: control.width
        padding: 6
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 280)
        background: Rectangle { color: theme.state.elevated; radius: 10; border.color: theme.state.stroke }
        contentItem: ListView {
            id: options
            objectName: "options-" + control.objectName
            clip: true
            implicitHeight: contentHeight
            boundsBehavior: control.subtleOverscroll ? Flickable.StopAtBounds : Flickable.DragAndOvershootBounds
            property real elasticOffset: 0
            contentItem.transform: Translate { y: options.elasticOffset }
            // Keep native scrolling bounded; the independent pulse never adds
            // to contentY or accumulates across repeated wheel events.
            WheelHandler {
                target: null
                blocking: false
                enabled: control.subtleOverscroll
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: function(event) {
                    const delta = event.pixelDelta.y || event.angleDelta.y
                    const bottom = options.originY + Math.max(0, options.contentHeight - options.height)
                    const atEdge = delta > 0 && options.contentY <= options.originY + 0.5
                        || delta < 0 && options.contentY >= bottom - 0.5
                    if (atEdge) {
                        rebound.stop()
                        options.elasticOffset = motion.reduced ? 0 : (delta > 0 ? 6 : -6)
                        if (!motion.reduced) rebound.restart()
                    }
                    event.accepted = false
                }
            }
            NumberAnimation {
                id: rebound
                target: options
                property: "elasticOffset"
                to: 0
                duration: motion.fast
                easing.type: motion.easing
            }
            model: control.popup.visible ? control.delegateModel : null
            // Hover is a visual state, not a request to scroll the viewport.
            currentIndex: control.currentIndex
            ScrollBar.vertical: UiScrollBar { compact: true }
        }
        onClosed: { rebound.stop(); options.elasticOffset = 0 }
        enter: UiPopupEnter { }
        exit: UiPopupExit { }
    }
}

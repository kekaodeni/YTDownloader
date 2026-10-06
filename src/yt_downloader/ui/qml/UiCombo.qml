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
    property bool subtleOverscroll: true
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
            // All dropdowns share bounded native scrolling. The optional pulse
            // moves only visual content, never the viewport or scrollbar.
            boundsBehavior: Flickable.StopAtBounds
            property real elasticOffset: 0
            property int feedbackDirection: 0
            contentItem.transform: Translate { y: options.elasticOffset }
            function cancelFeedback() {
                rebound.stop()
                elasticOffset = 0
            }
            function atFeedbackEdge(direction) {
                const bottom = originY + Math.max(0, contentHeight - height)
                return direction > 0 ? contentY <= originY + 0.5 : contentY >= bottom - 0.5
            }
            onContentYChanged: {
                if (rebound.running && !atFeedbackEdge(feedbackDirection)) cancelFeedback()
            }
            // One outward gesture starts one complete pulse. Events during
            // that pulse keep native scrolling, without resetting translation.
            WheelHandler {
                target: null
                blocking: false
                enabled: control.subtleOverscroll
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: function(event) {
                    const delta = event.pixelDelta.y || event.angleDelta.y
                    if (delta !== 0) {
                        const direction = delta > 0 ? 1 : -1
                        if (rebound.running && direction !== options.feedbackDirection) options.cancelFeedback()
                        if (!motion.reduced && options.atFeedbackEdge(direction) && !rebound.running) {
                            options.feedbackDirection = direction
                            rebound.start()
                        }
                    }
                    event.accepted = false
                }
            }
            SequentialAnimation {
                id: rebound
                NumberAnimation {
                    target: options; property: "elasticOffset"
                    to: options.feedbackDirection * 4
                    duration: 50; easing.type: motion.easing
                }
                NumberAnimation {
                    target: options; property: "elasticOffset"
                    to: 0
                    duration: 100; easing.type: motion.easing
                }
            }
            Connections {
                target: motion
                function onReducedChanged() { if (motion.reduced) options.cancelFeedback() }
            }
            model: control.popup.visible ? control.delegateModel : null
            // Hover is a visual state, not a request to scroll the viewport.
            currentIndex: control.currentIndex
            ScrollBar.vertical: UiScrollBar { compact: true }
        }
        onClosed: options.cancelFeedback()
        enter: UiPopupEnter { }
        exit: UiPopupExit { }
    }
}

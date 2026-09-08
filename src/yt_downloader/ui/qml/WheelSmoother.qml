import QtQuick

Item {
    id: root
    required property var view
    property int lastDirection: 0
    property int eventCount: 0
    SmoothedAnimation { id: animation; target: root.view; property: "contentY"; duration: 160; velocity: -1 }
    function limit(value) {
        const origin = root.view.originY || 0
        return Math.max(origin, Math.min(origin + Math.max(0, root.view.contentHeight - root.view.height), value))
    }
    WheelHandler {
        parent: root.view
        target: null
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function(event) {
            root.eventCount++
            if (!event.pixelDelta.y && !event.angleDelta.y) { event.accepted = false; return }
            root.view.cancelFlick()
            if (event.pixelDelta.y !== 0 || shell.state.reduceMotion) {
                animation.stop()
                root.view.contentY = root.limit(root.view.contentY - (event.pixelDelta.y || event.angleDelta.y / 120 * 64))
                root.lastDirection = 0
            } else {
                const direction = Math.sign(event.angleDelta.y)
                const start = animation.running && direction === root.lastDirection ? animation.to : root.view.contentY
                const destination = root.limit(start - event.angleDelta.y / 120 * 64)
                animation.stop()
                animation.to = destination
                animation.start()
                root.lastDirection = direction
            }
            event.accepted = true
        }
    }
    function stop() { animation.stop(); root.lastDirection = 0 }
    Connections { target: root.view; function onDraggingChanged() { if (root.view.dragging) root.stop() } }
    Connections { target: shell; function onChanged() { if (shell.state.reduceMotion) root.stop() } }
}

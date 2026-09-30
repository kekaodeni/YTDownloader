import QtQuick

// ListView lays an inline header out above originY. Resizing that header
// moves originY and can also reposition contentY. Keep the logical offset
// from the header top through the whole layout, including animated changes.
QtObject {
    id: anchor
    required property var view
    required property var header
    property real offset: 0
    property bool pending: false
    property var target: null
    property real headerHeight: header ? header.height : 0
    property real settledOrigin: 0
    property int stableFrames: 0
    property bool positioning: false

    function schedule() {
        pending = true
        stableFrames = 0
        Qt.callLater(settle)
    }
    function positionAt(item) {
        target = item
        schedule()
    }
    function settle() {
        view.forceLayout()
        if (target) {
            offset = target.mapToItem(view.contentItem, 0, 0).y - view.originY
            target = null
        }
        positioning = true
        view.contentY = view.originY + offset
        positioning = false
        headerHeight = header.height
        settledOrigin = view.originY
    }
    // Qt may reposition the view again during its polish pass. Finish only
    // after geometry has settled, rather than treating that move as a scroll.
    property FrameAnimation release: FrameAnimation {
        running: anchor.pending
        onTriggered: {
            const stable = anchor.header.height === anchor.headerHeight
                        && anchor.view.originY === anchor.settledOrigin
            anchor.positioning = true
            anchor.view.contentY = anchor.view.originY + anchor.offset
            anchor.positioning = false
            anchor.stableFrames = stable ? anchor.stableFrames + 1 : 0
            if (anchor.stableFrames >= 2) {
                // A collapse can remove content below the viewport. Clamp only
                // after layout settles, so the view never exposes blank space.
                anchor.offset = Math.max(0, Math.min(anchor.offset,
                                     Math.max(0, anchor.view.contentHeight - anchor.view.height)))
                anchor.positioning = true
                anchor.view.contentY = anchor.view.originY + anchor.offset
                anchor.positioning = false
                anchor.pending = false
            }
        }
    }
    property Connections geometry: Connections {
        target: anchor.header
        function onHeightChanged() { anchor.schedule() }
    }
    property Connections viewport: Connections {
        target: anchor.view
        function onOriginYChanged() { anchor.schedule() }
        function onContentYChanged() {
            if (anchor.positioning) return
            if (anchor.pending || anchor.header.height !== anchor.headerHeight) anchor.schedule()
            else anchor.offset = anchor.view.contentY - anchor.view.originY
        }
    }
}

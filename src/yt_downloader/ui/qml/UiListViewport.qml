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
    property bool positioning: false
    property bool bottomAnchored: false
    property real bottomDistance: 0
    property bool mutating: false
    property real mutationHeaderHeight: 0
    property real renderedMutationHeader: -1
    property real renderedMutationContent: -1

    function prepare(item) {
        mutating = true
        const viewportHeight = view.height
        const oldContentHeight = view.contentHeight
        const oldContentY = view.contentY
        mutationHeaderHeight = header.height
        renderedMutationHeader = -1
        renderedMutationContent = -1
        const anchorY = item.mapToItem(view, 0, 0).y
        // The controls precede the region they resize inside the same inline
        // header. Its logical offset preserves their captured screen Y.
        offset = item.mapToItem(view.contentItem, 0, 0).y - view.originY - anchorY
        const maximum = Math.max(0, oldContentHeight - viewportHeight)
        bottomDistance = Math.max(0, maximum - (oldContentY - view.originY))
        bottomAnchored = maximum > 0 && bottomDistance <= 6
        schedule()
    }

    function schedule() {
        pending = true
        Qt.callLater(settle)
    }
    function positionAt(item) {
        target = item
        schedule()
    }
    function settle() {
        if (mutating) return
        if (target) {
            offset = target.mapToItem(view.contentItem, 0, 0).y - view.originY
            target = null
        }
        restore()
        offset = view.contentY - view.originY
        headerHeight = header.height
        pending = false
        bottomAnchored = false
    }
    function finishMutation() {
        // Only release bookkeeping after the corrected geometry was rendered.
        // Position changes happen synchronously in geometry handlers, never
        // here or on the following frame.
        if (!mutating) return
        // A frame can swap before ListView has polished the resized header.
        // Keep the transaction until changed geometry has rendered stably.
        // Rows can also change height during a download, so do not require
        // the content delta to equal only the header delta.
        const headerDelta = header.height - mutationHeaderHeight
        if (Math.abs(headerDelta) < 0.5) return
        if (renderedMutationHeader !== header.height || renderedMutationContent !== view.contentHeight) {
            renderedMutationHeader = header.height
            renderedMutationContent = view.contentHeight
            return
        }
        offset = view.contentY - view.originY
        headerHeight = header.height
        mutating = false
        pending = false
        bottomAnchored = false
    }
    property Connections frame: Connections {
        target: anchor.view.Window.window
        function onFrameSwapped() { anchor.finishMutation() }
    }
    function restore() {
        const maximum = Math.max(0, view.contentHeight - view.height)
        // originY and contentHeight can notify separately in one polish pass.
        // Keep the desired logical offset until both have settled; clamping
        // that stored value against an intermediate height loses the anchor.
        const desired = bottomAnchored ? maximum - bottomDistance : offset
        positioning = true
        view.contentY = view.originY + Math.max(0, Math.min(desired, maximum))
        positioning = false
    }
    property Connections geometry: Connections {
        target: anchor.header
        function onHeightChanged() { anchor.schedule() }
    }
    property Connections viewport: Connections {
        target: anchor.view
        // Correct the inline-header origin during the same polish pass, before
        // the scene graph renders. A next-frame correction exposes a jump.
        function onOriginYChanged() { anchor.restore(); anchor.schedule() }
        function onContentHeightChanged() { anchor.restore(); anchor.schedule() }
        function onContentYChanged() {
            if (anchor.positioning) return
            if (anchor.pending || anchor.header.height !== anchor.headerHeight) {
                anchor.restore()
                anchor.schedule()
            }
            else anchor.offset = anchor.view.contentY - anchor.view.originY
        }
    }
}

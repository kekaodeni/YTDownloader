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
    property real boundaryReserve: 0
    property real boundaryTarget: 0
    property bool finishingBoundary: false
    property bool removingLastTask: false
    property bool removalAnimating: false
    property bool rowsChanging: false
    property SequentialAnimation removalHold: SequentialAnimation {
        PauseAnimation { duration: (anchor.rowsChanging ? motion.standard : motion.fast) + 32 }
        ScriptAction { script: { anchor.removalAnimating = false; anchor.view.Window.window.update() } }
    }
    onOffsetChanged: if (boundary.running) {
        boundaryReserve = Math.max(0, offset - boundaryTarget)
        restore()
    }
    property NumberAnimation boundary: NumberAnimation {
        target: anchor; property: "offset"
        duration: motion.geometry
        easing.type: motion.easing
        onFinished: {
            anchor.mutating = true
            anchor.pending = true
            anchor.finishingBoundary = true
            anchor.renderedMutationHeader = -1
            anchor.renderedMutationContent = -1
            anchor.boundaryReserve = 0
            anchor.restore()
        }
    }

    function prepare(item, shrinkingHeight = 0, removingLast = false) {
        rowsChanging = false
        boundary.stop()
        finishingBoundary = false
        removingLastTask = removingLast
        removalAnimating = removingLast
        if (removingLast) removalHold.restart()
        else removalHold.stop()
        boundaryReserve = 0
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
        // Empty lists have no task below the disclosure to anchor to. Preserve
        // the clicked control, reserving shrinkage only for this transaction.
        bottomAnchored = !removingLast && view.count > 0 && maximum > 0 && bottomDistance <= 6
        if (view.count === 0 || removingLast) boundaryReserve = Math.max(0, shrinkingHeight)
        schedule()
    }

    function prepareRows() {
        // Reserve the old extent through aggregation and disclosure. The
        // viewport stays put; if the new extent is shorter, clamp smoothly.
        prepare(header, Math.max(0, view.contentHeight - header.height), true)
        rowsChanging = true
        bottomAnchored = false
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
        if (mutating || boundary.running) return
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
        if (removingLastTask && removalAnimating) return
        // A frame can swap before ListView has polished the resized header.
        // Keep the transaction until changed geometry has rendered stably.
        // Rows can also change height during a download, so do not require
        // the content delta to equal only the header delta.
        const headerDelta = header.height - mutationHeaderHeight
        if (!rowsChanging && !removingLastTask && !finishingBoundary && Math.abs(headerDelta) < 0.5) return
        if (renderedMutationHeader !== header.height || renderedMutationContent !== view.contentHeight) {
            renderedMutationHeader = header.height
            renderedMutationContent = view.contentHeight
            view.Window.window.update()
            return
        }
        // The last native empty-list polish may reset contentY before its
        // notifications arrive. Commit our boundary target, not that reset.
        if (finishingBoundary) restore()
        offset = view.contentY - view.originY
        headerHeight = header.height
        mutating = false
        finishingBoundary = false
        pending = false
        bottomAnchored = false
        boundaryTarget = Math.min(offset, Math.max(0, view.contentHeight - boundaryReserve - view.height))
        if (boundaryReserve > 0 && offset > boundaryTarget) {
            // ListView can reset contentY when the animated footer reaches
            // zero. Keep the logical offset authoritative through that last
            // polish pass, including the animation's final value notification.
            pending = true
            boundary.from = offset
            boundary.to = boundaryTarget
            boundary.start()
        } else {
            if (boundaryReserve > 0) {
                // Footer removal itself is an empty-ListView layout mutation.
                mutating = true
                pending = true
                finishingBoundary = true
                renderedMutationHeader = -1
                renderedMutationContent = -1
            }
            boundaryReserve = 0
            restore()
            if (mutating) view.Window.window.update()
        }
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

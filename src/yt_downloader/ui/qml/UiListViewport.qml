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

    function schedule() {
        pending = true
        Qt.callLater(settle)
    }
    function positionAt(item) {
        target = item
        schedule()
    }
    function settle() {
        if (target) {
            offset = target.mapToItem(view.contentItem, 0, 0).y - view.originY
            target = null
        }
        offset = Math.max(0, Math.min(offset,
                              Math.max(0, view.contentHeight - view.height)))
        restore()
        headerHeight = header.height
        pending = false
    }
    function restore() {
        positioning = true
        view.contentY = view.originY + offset
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

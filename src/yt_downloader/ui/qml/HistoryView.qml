import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
Item {
    id: root
    objectName: "historyPage"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32; spacing: 18
        RowLayout { objectName: "historyHeader"; Layout.fillWidth: true; spacing: 6
            UiText { text: i18n.messages["history.title"]; role: "PageTitle" }
            Item { Layout.fillWidth: true }
            UiButton { objectName: "historyManageButton"; visible: !history.state.managing; text: i18n.messages["history.manage"]; onClicked: history.manage(true) }
        }
        UiText { Layout.fillWidth: true; text: i18n.messages["history.intro"]; role: "Secondary"; color: theme.state.secondary }
        Flow {
            id: managementToolbar
            objectName: "historyManagementToolbar"
            Layout.fillWidth: true
            spacing: 10
            visible: history.state.managing
            RowLayout {
                id: selectionGroup
                objectName: "historySelectionGroup"
                width: implicitWidth; height: 38; spacing: 14
                CheckBox {
                    id: selectAllCheck
                    objectName: "historySelectAll"
                    text: i18n.messages["history.select_all"]
                    tristate: true
                    checkState: history.state.selectAllState
                    nextCheckState: function() { return history.state.selectAllState }
                    enabled: history.state.selectableCount > 0
                    function activateSelectAll() { history.selectAll(history.state.selectAllState !== Qt.Checked) }
                    onClicked: activateSelectAll()
                    Keys.onReturnPressed: function(event) { event.accepted = true; activateSelectAll() }
                    Keys.onEnterPressed: function(event) { event.accepted = true; activateSelectAll() }
                    hoverEnabled: true
                    leftPadding: 8; rightPadding: 8; topPadding: 0; bottomPadding: 0; spacing: 8
                    implicitWidth: indicator.width + spacing + contentItem.implicitWidth + leftPadding + rightPadding
                    implicitHeight: 38
                    Layout.alignment: Qt.AlignVCenter
                    font.family: theme.fontFamily("Button", "全选")
                    font.pointSize: theme.fontSize("Button")
                    font.weight: theme.fontWeight("Button")
                    Accessible.role: Accessible.CheckBox
                    Accessible.name: i18n.messages["history.select_all"]
                    Accessible.description: checkState === Qt.Checked ? i18n.messages["history.selection.all"] : checkState === Qt.PartiallyChecked ? i18n.messages["history.selection.partial"] : i18n.messages["history.selection.unselected"]
                    indicator: Rectangle {
                        objectName: "historySelectAllIndicator"
                        x: selectAllCheck.leftPadding
                        y: (selectAllCheck.height - height) / 2
                        width: 18; height: 18; radius: 5
                        color: !selectAllCheck.enabled ? theme.state.subtle
                            : selectAllCheck.checkState !== Qt.Unchecked ? theme.state.accent
                            : selectAllCheck.hovered ? theme.state.subtle : theme.state.surface
                        Behavior on color { ColorAnimation { duration: motion.micro } }
                        border.width: selectAllCheck.visualFocus ? 2 : 1
                        border.color: selectAllCheck.visualFocus ? theme.state.accent
                            : selectAllCheck.checkState !== Qt.Unchecked ? theme.state.accent : theme.state.stroke
                        Text {
                            objectName: "historySelectAllCheckMark"
                            anchors.centerIn: parent
                            text: "✓"
                            visible: selectAllCheck.checkState === Qt.Checked
                            color: theme.state.onAccent
                            font.pixelSize: 12
                            font.weight: Font.Bold
                        }
                        Text {
                            objectName: "historySelectAllPartialMark"
                            anchors.centerIn: parent
                            text: "−"
                            visible: selectAllCheck.checkState === Qt.PartiallyChecked
                            color: theme.state.onAccent
                            font.pixelSize: 12
                            font.weight: Font.Bold
                        }
                    }
                    contentItem: UiText {
                        leftPadding: selectAllCheck.indicator.width + selectAllCheck.spacing
                        text: selectAllCheck.text
                        color: selectAllCheck.enabled ? theme.state.text : theme.state.disabled
                        verticalAlignment: Text.AlignVCenter
                        font: selectAllCheck.font
                    }
                }
                UiText {
                    id: selectedCount
                    objectName: "historySelectedCount"
                    text: history.state.managementText
                    role: "Caption"
                    color: theme.state.secondary
                    Accessible.name: text
                    Layout.alignment: Qt.AlignVCenter
                }
            }
            Item {
                width: Math.max(0, managementToolbar.width - selectionGroup.implicitWidth - actionGroup.implicitWidth - managementToolbar.spacing * 2)
                height: 1
            }
            RowLayout {
                id: actionGroup
                objectName: "historyActionGroup"
                width: implicitWidth; height: 38; spacing: 10
                UiButton { objectName: "historyDeleteSelected"; text: i18n.messages["history.delete_selected"]; appearance: "danger"; enabled: history.state.checkedCount > 0; onClicked: history.deleteChecked() }
                UiButton { objectName: "historyClear"; text: i18n.messages["history.clear"]; onClicked: history.clearTerminal() }
                UiButton { objectName: "historyManageToggle"; text: i18n.messages["common.done"]; appearance: "primary"; onClicked: history.manage(false) }
            }
        }
        ListView {
            id: list
            objectName: "historyList"
            Layout.fillWidth: true; Layout.fillHeight: true
            model: history.model; reuseItems: true; clip: true; spacing: 5
            boundsBehavior: Flickable.StopAtBounds
            keyNavigationEnabled: true
            function syncSelectedIndex() {
                const selectedIndex = history.state.selectedIndex
                if (currentIndex !== selectedIndex) currentIndex = selectedIndex
            }
            Component.onCompleted: syncSelectedIndex()
            Connections {
                target: history
                function onChanged() { list.syncSelectedIndex() }
            }
            onCurrentIndexChanged: if (currentIndex >= 0 && history.model.get(currentIndex).id !== history.state.selectedId) history.select(history.model.get(currentIndex).id)
            ScrollBar.vertical: ScrollBar { onPressedChanged: if (pressed) wheel.stop() }
            WheelSmoother { id: wheel; view: list }
            Keys.onPressed: function(event) {
                wheel.stop()
                if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
                    if (history.state.selectedId && list.currentItem) contextMenu.popup(list.currentItem, 24, list.currentItem.height - 4)
                    event.accepted = true
                } else if (history.state.managing && (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                    history.toggle(history.state.selectedId); event.accepted = true
                } else if (history.state.managing && event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
                    history.selectAll(true); event.accepted = true
                } else if (history.state.managing && event.key === Qt.Key_Delete) {
                    history.deleteChecked(); event.accepted = true
                }
            }
            delegate: Rectangle {
                id: historyRow
                required property var item
                objectName: "history-" + item.id
                Component.onCompleted: history.requestThumbnail(item.id)
                onItemChanged: history.requestThumbnail(item.id)
                ListView.onReused: history.requestThumbnail(item.id)
                width: list.width - 10; height: row.implicitHeight + 24; radius: 10
                property bool rowSelected: history.state.managing ? item.checked : item.id === history.state.selectedId
                property int rowCursorShape: hover.cursorShape
                // Interpolate opaque theme colors; transparent black darkens
                // the midpoint of an otherwise subtle hover transition.
                color: rowSelected ? theme.state.selection : hover.hovered ? theme.state.subtle : theme.state.canvas
                Behavior on color { ColorAnimation { duration: motion.micro } }
                // Selection persists while menus/dialogs own keyboard focus.
                border.width: rowSelected ? 1 : 0
                border.color: theme.state.accent
                Rectangle {
                    objectName: "historyFocus-" + item.id
                    visible: list.activeFocus && item.id === history.state.selectedId
                    anchors.left: parent.left; anchors.leftMargin: 12
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                    width: 24; height: 2; radius: 1; color: theme.state.accent
                }
                Accessible.role: Accessible.ListItem
                Accessible.name: item.title + "，" + i18n.messages[item.statusKey]
                HoverHandler {
                    id: hover
                    cursorShape: history.state.managing && item.deletable ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: function(point, button) {
                        history.prepareContext(item.id); list.forceActiveFocus()
                        contextMenu.popup(historyRow, point.position.x, point.position.y)
                    }
                }
                MouseArea {
                    objectName: "historyRowHitTarget-" + item.id
                    anchors.fill: parent
                    z: -1
                    acceptedButtons: Qt.LeftButton
                    onClicked: {
                        list.forceActiveFocus()
                        if (history.state.managing) history.toggle(item.id)
                        else history.select(item.id)
                    }
                }
                RowLayout { id: row; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 14
                    CheckBox {
                        id: selectCheck
                        objectName: "historySelect-" + item.id
                        visible: history.state.managing
                        enabled: item.deletable
                        checked: item.checked
                        implicitWidth: 24; implicitHeight: 24
                        Layout.preferredWidth: 24; Layout.preferredHeight: 24
                        Layout.alignment: Qt.AlignVCenter
                        padding: 0
                        Accessible.name: i18n.messages["action.select_item"].replace("{title}", item.title)
                        onClicked: history.toggle(item.id)
                        indicator: Rectangle {
                            objectName: "historyCheckboxIndicator-" + item.id
                            x: (selectCheck.width - width) / 2
                            y: (selectCheck.height - height) / 2
                            width: 18; height: 18; radius: 5
                            color: !selectCheck.enabled ? theme.state.subtle : selectCheck.checked ? theme.state.accent : selectCheck.hovered ? theme.state.subtle : theme.state.surface
                            Behavior on color { ColorAnimation { duration: motion.micro } }
                            border.width: selectCheck.visualFocus ? 2 : 1
                            border.color: selectCheck.visualFocus ? theme.state.accent : selectCheck.checked ? theme.state.accent : theme.state.stroke
                            Text {
                                anchors.centerIn: parent
                                text: "✓"
                                visible: selectCheck.checked
                                color: theme.state.onAccent
                                font.pixelSize: 12
                                font.weight: Font.Bold
                            }
                        }
                        contentItem: Item { }
                    }
                    Item {
                        Layout.preferredWidth: root.width < 620 ? 72 : 112
                        Layout.preferredHeight: root.width < 620 ? 76 : 88
                        Thumbnail {
                            id: historyCover
                            objectName: "historyCover-" + item.id
                            anchors.centerIn: parent
                            width: Math.min(parent.width, parent.height * sourceAspectRatio)
                            height: width / sourceAspectRatio
                            imageFillMode: Image.PreserveAspectFit
                            source: item.thumbnail; placeholder: i18n.messages["thumbnail.video"]
                        }
                    }
                    ColumnLayout { Layout.fillWidth: true; spacing: 6
                        UiText { objectName: "historyTitle-" + item.id; Layout.fillWidth: true; text: item.title; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
                        UiText { objectName: "historySubtitle-" + item.id; Layout.fillWidth: true; text: item.subtitle; role: "Caption"; color: theme.state.secondary; elide: Text.ElideRight }
                        UiText { objectName: "historyStatusMobile-" + item.id; visible: root.width < 620; text: i18n.messages[item.statusKey]; role: "Caption"; color: theme.state.secondary }
                    }
                    UiText { objectName: "historyStatus-" + item.id; visible: root.width >= 620; text: i18n.messages[item.statusKey]; role: "Caption"; color: theme.state.secondary }
                }
            }
            Column { anchors.centerIn: parent; width: parent.width; spacing: 10; visible: history.model.count === 0
                UiText { width: parent.width; text: i18n.messages["history.empty.title"]; role: "SectionTitle"; horizontalAlignment: Text.AlignHCenter }
                UiText { width: parent.width; text: i18n.messages["history.empty.body"]; role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
            }
        }
        Flow { Layout.fillWidth: true; spacing: 8; visible: !history.state.managing
            UiButton { objectName: "historyItemOpen"; text: i18n.messages["action.open_file"]; enabled: history.state.fileExists; onClicked: history.action("open") }
            UiButton { objectName: "historyItemFolder"; text: i18n.messages["action.open_folder"]; enabled: history.state.fileExists; onClicked: history.action("folder") }
            UiButton { objectName: "historyItemCopy"; text: i18n.messages["action.copy_link"]; enabled: history.state.selectedId.length > 0; onClicked: history.action("copy") }
            UiButton { objectName: "historyItemCover"; text: i18n.messages["action.set_video_cover"]; enabled: history.state.fileExists; onClicked: history.action("cover") }
            UiButton { objectName: "historyItemRetry"; text: i18n.messages["action.retry"]; enabled: history.state.selectedId.length > 0; onClicked: history.action("retry") }
        }
    }
    UiMenu {
        id: contextMenu; objectName: "historyMenu"
        onClosed: list.forceActiveFocus()
        UiMenuItem { text: i18n.messages["action.open_file"]; icon.source: assetsBase + "icons/open_regular.svg"; enabled: history.state.fileExists; onTriggered: history.action("open") }
        UiMenuItem { text: i18n.messages["action.open_folder"]; icon.source: assetsBase + "icons/folder_regular.svg"; enabled: history.state.fileExists; onTriggered: history.action("folder") }
        UiMenuItem { text: i18n.messages["action.copy_link"]; icon.source: assetsBase + "icons/link_regular.svg"; onTriggered: history.action("copy") }
        UiMenuItem { text: i18n.messages["action.redownload"]; icon.source: assetsBase + "icons/retry_regular.svg"; onTriggered: history.action("retry") }
        UiMenuItem { text: i18n.messages["action.set_video_cover"]; icon.source: assetsBase + "icons/image_regular.svg"; enabled: history.state.fileExists; onTriggered: history.action("cover") }
        UiMenuSeparator { }
        UiMenuItem { objectName: "historyContextDelete"; text: history.state.managing && history.state.checkedCount > 1 ? i18n.messages["history.delete_selected"] : i18n.messages["action.delete_record"]; destructive: true; icon.source: assetsBase + "icons/delete_regular.svg"; enabled: history.state.canDelete; onTriggered: history.action("delete") }
    }
}

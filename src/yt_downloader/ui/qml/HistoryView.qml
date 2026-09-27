import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
Item {
    id: root
    objectName: "historyPage"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32; spacing: 18
        RowLayout { objectName: "historyHeader"; Layout.fillWidth: true; spacing: 6
            UiText { text: "历史记录"; role: "PageTitle" }
            Item { Layout.fillWidth: true }
            CheckBox {
                id: selectAllCheck
                objectName: "historySelectAll"
                visible: history.state.managing
                text: "全选"
                enabled: history.state.selectableCount > 0
                tristate: true
                checkState: history.state.selectAllState
                nextCheckState: function() { return history.state.selectAllState }
                onClicked: history.selectAll(history.state.selectAllState !== Qt.Checked)
                hoverEnabled: true
                leftPadding: 14; rightPadding: 14; topPadding: 0; bottomPadding: 0; spacing: 8
                implicitWidth: indicator.width + spacing + contentItem.implicitWidth + leftPadding + rightPadding
                implicitHeight: 38
                Layout.alignment: Qt.AlignVCenter
                font.family: theme.fontFamily("Button", "全选")
                font.pointSize: theme.fontSize("Button")
                font.weight: theme.fontWeight("Button")
                Accessible.name: "全选"
                scale: down && !shell.state.reduceMotion ? 0.985 : 1
                Behavior on scale { SmoothedAnimation { duration: 90; velocity: -1 } }
                indicator: Rectangle {
                    x: selectAllCheck.leftPadding
                    y: (selectAllCheck.height - height) / 2
                    width: 18; height: 18; radius: 5
                    color: !selectAllCheck.enabled ? theme.state.subtle : selectAllCheck.checkState !== Qt.Unchecked ? theme.state.accent : selectAllCheck.hovered ? theme.state.subtle : theme.state.surface
                    border.width: selectAllCheck.visualFocus ? 2 : 1
                    border.color: selectAllCheck.visualFocus ? theme.state.accent : selectAllCheck.checkState !== Qt.Unchecked ? theme.state.accent : theme.state.stroke
                    Text {
                        anchors.centerIn: parent
                        text: "✓"
                        visible: selectAllCheck.checkState === Qt.Checked
                        color: theme.state.onAccent
                        font.pixelSize: 12
                        font.weight: Font.Bold
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 9; height: 2; radius: 1
                        visible: selectAllCheck.checkState === Qt.PartiallyChecked
                        color: theme.state.onAccent
                    }
                }
                contentItem: UiText {
                    leftPadding: selectAllCheck.indicator.width + selectAllCheck.spacing
                    text: selectAllCheck.text
                    color: selectAllCheck.enabled ? theme.state.text : theme.state.disabled
                    verticalAlignment: Text.AlignVCenter
                    font: selectAllCheck.font
                }
                background: Rectangle {
                    objectName: "historySelectAllBackground"
                    radius: 8
                    color: !selectAllCheck.enabled ? theme.state.subtle : selectAllCheck.down ? theme.state.stroke : selectAllCheck.hovered ? theme.state.subtle : theme.state.surface
                    border.width: selectAllCheck.visualFocus ? 2 : 1
                    border.color: selectAllCheck.visualFocus ? theme.state.accent : theme.state.stroke
                    Behavior on color { ColorAnimation { duration: shell.state.reduceMotion ? 0 : 120 } }
                }
            }
            UiButton { objectName: "historyDeleteSelected"; visible: history.state.managing; text: "删除所选"; appearance: "danger"; enabled: history.state.checkedCount > 0; onClicked: history.deleteChecked() }
            UiButton { objectName: "historyClear"; visible: history.state.managing; text: "清空历史"; onClicked: history.clearTerminal() }
            UiButton { objectName: "historyManageToggle"; text: history.state.managing ? "完成" : "管理"; appearance: history.state.managing ? "primary" : "normal"; onClicked: history.manage(!history.state.managing) }
        }
        UiText { Layout.fillWidth: true; text: "通过本软件下载的内容，都在这里。"; role: "Secondary"; color: theme.state.secondary }
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
                color: rowSelected ? theme.state.selection : hover.hovered ? theme.state.subtle : "transparent"
                border.width: rowSelected && list.activeFocus ? 1 : 0
                border.color: theme.state.accent
                Accessible.role: Accessible.ListItem
                Accessible.name: item.title + "，" + item.status
                HoverHandler {
                    id: hover
                    cursorShape: history.state.managing && item.deletable ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: function(point, button) {
                        history.select(item.id); list.forceActiveFocus()
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
                        Accessible.name: "选择 " + item.title
                        onClicked: history.toggle(item.id)
                        indicator: Rectangle {
                            objectName: "historyCheckboxIndicator-" + item.id
                            x: (selectCheck.width - width) / 2
                            y: (selectCheck.height - height) / 2
                            width: 18; height: 18; radius: 5
                            color: !selectCheck.enabled ? theme.state.subtle : selectCheck.checked ? theme.state.accent : selectCheck.hovered ? theme.state.subtle : theme.state.surface
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
                            source: item.thumbnail; placeholder: "视频"
                        }
                    }
                    ColumnLayout { Layout.fillWidth: true; spacing: 6
                        UiText { objectName: "historyTitle-" + item.id; Layout.fillWidth: true; text: item.title; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
                        UiText { objectName: "historySubtitle-" + item.id; Layout.fillWidth: true; text: item.subtitle; role: "Caption"; color: theme.state.secondary; elide: Text.ElideRight }
                        UiText { objectName: "historyStatusMobile-" + item.id; visible: root.width < 620; text: item.status; role: "Caption"; color: theme.state.secondary }
                    }
                    UiText { objectName: "historyStatus-" + item.id; visible: root.width >= 620; text: item.status; role: "Caption"; color: theme.state.secondary }
                }
            }
            Column { anchors.centerIn: parent; width: parent.width; spacing: 10; visible: history.model.count === 0
                UiText { width: parent.width; text: "还没有下载记录"; role: "SectionTitle"; horizontalAlignment: Text.AlignHCenter }
                UiText { width: parent.width; text: "完成下载后，你可以在这里打开文件或设置视频封面。"; role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
            }
        }
        ColumnLayout { Layout.fillWidth: true; visible: history.state.managing; spacing: 8
            UiText { text: history.state.managementText; role: "Caption"; color: theme.state.secondary }
        }
        Flow { Layout.fillWidth: true; spacing: 8
            UiButton { text: "打开文件"; enabled: history.state.fileExists; onClicked: history.action("open") }
            UiButton { text: "打开文件夹"; enabled: history.state.fileExists; onClicked: history.action("folder") }
            UiButton { text: "复制链接"; enabled: history.state.selectedId.length > 0; onClicked: history.action("copy") }
            UiButton { text: "设置视频封面"; enabled: history.state.fileExists; onClicked: history.action("cover") }
            UiButton { text: "重试"; enabled: history.state.selectedId.length > 0; onClicked: history.action("retry") }
        }
    }
    UiMenu {
        id: contextMenu; objectName: "historyMenu"
        onClosed: list.forceActiveFocus()
        UiMenuItem { text: "打开文件"; icon.source: assetsBase + "icons/open_regular.svg"; enabled: history.state.fileExists; onTriggered: history.action("open") }
        UiMenuItem { text: "打开文件夹"; icon.source: assetsBase + "icons/folder_regular.svg"; enabled: history.state.fileExists; onTriggered: history.action("folder") }
        UiMenuItem { text: "复制链接"; icon.source: assetsBase + "icons/link_regular.svg"; onTriggered: history.action("copy") }
        UiMenuItem { text: "重新下载"; icon.source: assetsBase + "icons/retry_regular.svg"; onTriggered: history.action("retry") }
        UiMenuItem { text: "设置视频封面"; icon.source: assetsBase + "icons/image_regular.svg"; enabled: history.state.fileExists; onTriggered: history.action("cover") }
        UiMenuSeparator { }
        UiMenuItem { text: "删除记录"; destructive: true; icon.source: assetsBase + "icons/delete_regular.svg"; enabled: history.state.canDelete; onTriggered: history.action("delete") }
    }
}

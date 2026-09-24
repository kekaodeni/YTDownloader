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
            UiButton { objectName: "historySelectAll"; visible: history.state.managing; text: "全选"; onClicked: history.selectAll(true) }
            UiButton { objectName: "historySelectNone"; visible: history.state.managing; text: "取消全选"; enabled: history.state.checkedCount > 0; onClicked: history.selectAll(false) }
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
            currentIndex: history.state.selectedIndex
            keyNavigationEnabled: true
            onCurrentIndexChanged: if (currentIndex >= 0) history.select(history.model.get(currentIndex).id)
            ScrollBar.vertical: ScrollBar { onPressedChanged: if (pressed) wheel.stop() }
            WheelSmoother { id: wheel; view: list }
            Keys.onPressed: function(event) {
                wheel.stop()
                if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
                    if (history.state.selectedId && list.currentItem) contextMenu.popup(list.currentItem, 24, list.currentItem.height - 4)
                    event.accepted = true
                } else if (history.state.managing && event.key === Qt.Key_Space) {
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
                color: item.id === history.state.selectedId ? theme.state.selection : hover.hovered ? theme.state.subtle : "transparent"
                border.width: item.id === history.state.selectedId && list.activeFocus ? 1 : 0
                border.color: theme.state.accent
                Accessible.role: Accessible.ListItem
                Accessible.name: item.title + "，" + item.status
                HoverHandler { id: hover }
                TapHandler {
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onTapped: function(point, button) {
                        history.select(item.id); list.forceActiveFocus()
                        if (button === Qt.RightButton) contextMenu.popup(historyRow, point.position.x, point.position.y)
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
                        UiText { Layout.fillWidth: true; text: item.title; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
                        UiText { Layout.fillWidth: true; text: item.subtitle; role: "Caption"; color: theme.state.secondary; elide: Text.ElideRight }
                        UiText { visible: root.width < 620; text: item.status; role: "Caption"; color: theme.state.secondary }
                    }
                    UiText { visible: root.width >= 620; text: item.status; role: "Caption"; color: theme.state.secondary }
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

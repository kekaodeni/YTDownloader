import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: popup
    required property var session
    property var s: session.state
    property var restoreFocus
    property bool detailsOpen: false
    objectName: "dialog-" + s.kind
    modal: s.modal
    focus: true
    closePolicy: Popup.NoAutoClose
    Shortcut { sequence: "Escape"; enabled: popup.opened && popup.s.closeEnabled; onActivated: popup.session.reject() }
    width: Math.min(620, parent ? parent.width - 32 : 620)
    height: Math.min(implicitHeight, parent ? parent.height - 40 : 700)
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? (parent.height - height) / 2 : 0
    padding: 24
    title: s.title
    background: Rectangle { radius: 16; color: theme.state.elevated; border.color: theme.state.stroke }
    header: Item {
        implicitHeight: 66
        UiText { anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 24; anchors.verticalCenter: parent.verticalCenter; text: popup.s.title; role: "SectionTitle"; elide: Text.ElideRight }
    }
    Overlay.modal: Rectangle { color: "#550C1524" }
    onOpened: { cancelAction.forceActiveFocus() }
    onClosed: if (restoreFocus) restoreFocus.forceActiveFocus()
    Component.onCompleted: if (s.open) open()
    Connections {
        target: popup.session
        function onChanged() {
            if (popup.session.state.open && !popup.visible) {
                popup.restoreFocus = popup.parent && popup.parent.Window.window ? popup.parent.Window.window.activeFocusItem : null
                popup.open()
            } else if (!popup.session.state.open && popup.visible) popup.close()
        }
        function onFocusRequested() { popup.open(); cancelAction.forceActiveFocus() }
    }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: shell.state.reduceMotion ? 0 : 180; easing.type: Easing.OutCubic } }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: shell.state.reduceMotion ? 0 : 140 } }
    contentItem: ScrollView {
        id: viewport
        implicitHeight: body.implicitHeight
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            id: body; width: viewport.availableWidth; spacing: 16
            Keys.onEscapePressed: if (popup.s.closeEnabled) popup.session.reject()
            UiText { Layout.fillWidth: true; text: popup.s.message; wrapMode: Text.Wrap; color: theme.state.secondary }
            ColumnLayout {
                Layout.fillWidth: true; visible: popup.s.kind === "error"; spacing: 12
                UiButton { objectName: "errorDetails"; text: popup.detailsOpen ? "收起错误详情" : "错误详情"; appearance: "quiet"; onClicked: popup.detailsOpen = !popup.detailsOpen }
                ScrollView {
                    Layout.fillWidth: true; Layout.preferredHeight: 180; visible: popup.detailsOpen
                        TextArea { text: popup.s.details || ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: theme.state.text; selectionColor: theme.state.selection; selectedTextColor: theme.state.text; font.family: theme.fontFamily("Caption", text); font.pointSize: theme.fontSize("Caption"); font.weight: theme.fontWeight("Caption"); background: Rectangle { color: theme.state.subtle; radius: 8 } }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; visible: popup.s.kind === "update"; spacing: 12
                UiText { Layout.fillWidth: true; text: popup.s.notes || ""; wrapMode: Text.Wrap }
                UiProgress { Layout.fillWidth: true; visible: popup.s.progressVisible || false; value: popup.s.progress || 0 }
            }
            ColumnLayout {
                Layout.fillWidth: true; visible: popup.s.kind === "cover"; spacing: 12
                UiText { text: popup.s.durationText || ""; role: "Caption"; color: theme.state.muted }
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(120, Math.min(380, popup.parent ? popup.parent.height - 330 : 380, width / (popup.s.previewRatio || (16 / 9))))
                    Thumbnail {
                        objectName: "coverPreview"
                        anchors.centerIn: parent
                        width: Math.min(parent.width, parent.height * (popup.s.previewRatio || (16 / 9)))
                        height: width / (popup.s.previewRatio || (16 / 9))
                        imageFillMode: Image.PreserveAspectFit
                        source: popup.s.preview || ""
                        placeholder: popup.s.previewText || ""
                    }
                }
                Slider { Layout.fillWidth: true; from: 0; to: popup.s.duration || 0; value: popup.s.timestamp || 0; stepSize: 1; enabled: popup.s.controlsEnabled || false; Accessible.name: "封面时间"; onMoved: popup.session.setTimestamp(value) }
                RowLayout { Layout.fillWidth: true
                    UiText { text: "时间（秒）"; role: "Caption" }
                    UiField { Layout.fillWidth: true; text: (popup.s.timestamp || 0).toFixed(1); enabled: popup.s.controlsEnabled || false; Accessible.name: "封面时间（秒）"; validator: DoubleValidator { bottom: 0; top: popup.s.duration || 0; decimals: 1; locale: "C" } onEditingFinished: if (acceptableInput) popup.session.setTimestamp(Number(text)) }
                }
            }
        }
    }
    footer: Item {
        implicitHeight: actions.implicitHeight + 32
        Flow {
            id: actions
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 8
            UiButton { text: "复制错误报告"; visible: popup.s.kind === "error"; onClicked: popup.session.copyReport() }
            UiButton { text: "重试"; visible: popup.s.kind === "error" && (popup.s.hasRetry || false); onClicked: popup.session.retry() }
            UiButton { text: "打开文件夹"; visible: popup.s.kind === "confirm" && (popup.s.hasFolder || false); onClicked: popup.session.openFolder() }
            UiButton { text: popup.s.acceptText || ""; appearance: "danger"; visible: popup.s.kind === "confirm"; onClicked: popup.session.answer(true) }
            UiButton { text: "预览"; visible: popup.s.kind === "cover" && !popup.s.completed; enabled: popup.s.previewEnabled || false; onClicked: popup.session.generatePreview() }
            UiButton { text: popup.s.applyText || "写入视频封面"; appearance: "primary"; visible: popup.s.kind === "cover" && !popup.s.completed; enabled: popup.s.applyEnabled || false; onClicked: popup.session.apply() }
            UiButton { text: "资源管理器封面支持"; visible: popup.s.kind === "cover" && (popup.s.explorerNeedsSupport || false); onClicked: popup.session.openExplorerSupport() }
            UiButton { text: "打开发布页面"; visible: popup.s.kind === "update" && (popup.s.canRelease || false); onClicked: popup.session.action("release") }
            UiButton { text: "下载并验证"; appearance: "primary"; visible: popup.s.kind === "update" && (popup.s.canDownload || false); onClicked: popup.session.action("download") }
            UiButton { text: popup.s.cancelEnabled ? "取消下载" : "正在取消…"; enabled: popup.s.cancelEnabled || false; visible: popup.s.kind === "update" && (popup.s.canCancel || false); onClicked: popup.session.action("cancel") }
            UiButton { text: "退出并更新"; appearance: "primary"; visible: popup.s.kind === "update" && (popup.s.canInstall || false); onClicked: popup.session.action("install") }
            UiButton { id: cancelAction; objectName: "dialogCancel"; text: popup.s.kind === "confirm" ? popup.s.cancelText : popup.s.kind === "update" ? "稍后" : "关闭"; enabled: popup.s.closeEnabled; onClicked: popup.session.reject() }
        }
    }
}

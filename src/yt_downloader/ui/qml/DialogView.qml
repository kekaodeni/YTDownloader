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
            UiText { Layout.fillWidth: true; visible: popup.s.kind === "info"; text: "请只使用你自己的 Cookie，不要把 cookies.txt 分享给他人。YTDownloader 不会将 Cookie 上传到 GitHub，也不会写入下载历史。"; wrapMode: Text.Wrap; color: theme.state.secondary }
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
                UiText { objectName: "updateVersions"; Layout.fillWidth: true; text: "当前版本 " + (popup.s.currentVersion || "") + "  →  " + (popup.s.targetVersion || "") + "    ·    " + (popup.s.packageSize || ""); wrapMode: Text.Wrap; textFormat: Text.PlainText }
                UiCombo { objectName: "updateLanguage"; accessibleName: "更新说明语言"; model: ["中文", "English"]; currentIndex: popup.s.language === "en" ? 1 : 0; onActivated: popup.session.setLanguage(currentIndex === 1 ? "en" : "zh-CN") }
                ScrollView {
                    objectName: "updateNotesScroll"
                    Layout.fillWidth: true; Layout.preferredHeight: Math.min(160, Math.max(70, popup.height * 0.24))
                    clip: true; contentWidth: availableWidth
                    TextArea { objectName: "updateNotes"; text: popup.s.notes || ""; textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: theme.state.text; selectionColor: theme.state.selection; selectedTextColor: theme.state.text; font.family: theme.fontFamily("Body", text); font.pointSize: theme.fontSize("Body"); background: Rectangle { color: theme.state.subtle; radius: 8 } }
                }
                UiProgress { Layout.fillWidth: true; visible: popup.s.progressVisible || false; value: popup.s.progress || 0 }
                UiText { objectName: "updateProgressText"; Layout.fillWidth: true; visible: popup.s.progressVisible || false; text: popup.s.progressText || ""; role: "Caption"; wrapMode: Text.Wrap }
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
            ColumnLayout {
                Layout.fillWidth: true; visible: popup.s.kind === "cookie"; spacing: 10
                UiText { Layout.fillWidth: true; text: "配置名称只是这份登录状态配置的备注名称，例如“YouTube - Edge”。"; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiText { text: "Cookie 来源"; role: "Caption" }
                UiCombo { objectName: "cookieSourceCombo"; Layout.fillWidth: true; model: ["从浏览器读取", "cookies.txt"]; currentIndex: popup.s.source === "file" ? 1 : 0; onActivated: popup.session.setSource(currentIndex === 1 ? "file" : "browser") }
                UiText { text: "配置名称"; role: "Caption" }
                UiField { objectName: "cookieName"; Layout.fillWidth: true; text: popup.s.name || ""; onTextChanged: popup.session.setField("name", text) }
                UiText { text: "适用网站（可选）"; role: "Caption" }
                UiField { objectName: "cookieDomain"; Layout.fillWidth: true; text: popup.s.domain || ""; onTextChanged: popup.session.setField("domain", text); placeholderText: "例如 youtube.com" }
                UiCombo { objectName: "cookieBrowser"; visible: popup.s.source === "browser"; Layout.fillWidth: true; model: ["Chrome", "Edge", "Firefox", "Brave", "Opera", "Chromium"]; property var values: ["chrome", "edge", "firefox", "brave", "opera", "chromium"]; currentIndex: Math.max(0, values.indexOf(popup.s.browser)); onActivated: popup.session.setField("browser", values[currentIndex]) }
                UiField { objectName: "cookieBrowserProfile"; visible: popup.s.source === "browser"; Layout.fillWidth: true; text: popup.s.browserProfile || ""; placeholderText: "Default（可选）"; Accessible.name: "浏览器配置文件"; onTextChanged: popup.session.setField("browserProfile", text) }
                RowLayout { Layout.fillWidth: true; visible: popup.s.source === "file"
                    UiText { Layout.fillWidth: true; text: popup.s.fileLabel || "未选择文件"; role: "Caption"; elide: Text.ElideLeft }
                    UiButton { objectName: "cookieBrowse"; text: "浏览"; onClicked: popup.session.browse() }
                }
                UiText { Layout.fillWidth: true; text: popup.s.source === "file" ? "Cookie 文件相当于登录凭据，请勿分享给他人。" : "先在浏览器中登录目标网站；Cookie 内容只在解析时读取。"; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiText { Layout.fillWidth: true; text: popup.s.message || ""; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
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
            UiButton { text: "完整发布说明"; visible: popup.s.kind === "update" && (popup.s.canRelease || false); onClicked: popup.session.action("release") }
            UiButton { objectName: "updateDownload"; text: popup.s.downloadText || "下载并安装"; appearance: "primary"; visible: popup.s.kind === "update" && (popup.s.canDownload || false); onClicked: popup.session.action("download") }
            UiButton { text: popup.s.cancelEnabled ? "取消下载" : "正在取消…"; enabled: popup.s.cancelEnabled || false; visible: popup.s.kind === "update" && (popup.s.canCancel || false); onClicked: popup.session.action("cancel") }
            UiButton { objectName: "updateInstall"; text: "立即安装并重启"; appearance: "primary"; visible: popup.s.kind === "update" && (popup.s.canInstall || false); onClicked: popup.session.action("install") }
            UiButton { objectName: "cookieTest"; text: "测试配置"; visible: popup.s.kind === "cookie"; onClicked: popup.session.test() }
            UiButton { objectName: "cookieSave"; text: "保存"; appearance: "primary"; visible: popup.s.kind === "cookie"; onClicked: popup.session.save() }
            UiButton { id: cancelAction; objectName: "dialogCancel"; text: popup.s.kind === "confirm" ? popup.s.cancelText : popup.s.kind === "update" ? popup.s.dismissText : "关闭"; enabled: popup.s.closeEnabled; onClicked: popup.session.reject() }
        }
    }
}

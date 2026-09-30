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
    Overlay.modal: UiDimmer { }
    onOpened: { cancelAction.forceActiveFocus() }
    onClosed: if (restoreFocus) restoreFocus.forceActiveFocus()
    Component.onCompleted: if (s.open) open()
    Connections {
        target: popup.session
        ignoreUnknownSignals: true
        function onChanged() {
            if (popup.session.state.open && !popup.visible) {
                popup.restoreFocus = popup.parent && popup.parent.Window.window ? popup.parent.Window.window.activeFocusItem : null
                popup.open()
            } else if (!popup.session.state.open && popup.visible) popup.close()
        }
        function onFocusRequested() { popup.open(); cancelAction.forceActiveFocus() }
    }
    enter: UiPopupEnter { duration: motion.standard }
    exit: UiPopupExit { }
    contentItem: UiScrollView {
        id: viewport
        implicitHeight: body.implicitHeight
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            id: body; width: viewport.availableWidth; spacing: 16
            Keys.onEscapePressed: if (popup.s.closeEnabled) popup.session.reject()
            UiText { Layout.fillWidth: true; text: popup.s.message; wrapMode: Text.Wrap; color: theme.state.secondary }
            UiText { Layout.fillWidth: true; visible: popup.s.kind === "info"; text: i18n.messages["cookie.privacy_short"]; wrapMode: Text.Wrap; color: theme.state.secondary }
            ColumnLayout {
                Layout.fillWidth: true; visible: popup.s.kind === "error"; spacing: 12
                UiButton { objectName: "errorDetails"; text: popup.detailsOpen ? i18n.messages["error.hide_details"] : i18n.messages["error.details"]; appearance: "quiet"; onClicked: popup.detailsOpen = !popup.detailsOpen }
                UiScrollView {
                    Layout.fillWidth: true; Layout.preferredHeight: 180; visible: popup.detailsOpen
                        TextArea { text: popup.s.details || ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: theme.state.text; selectionColor: theme.state.selection; selectedTextColor: theme.state.text; font.family: theme.fontFamily("Caption", text); font.pointSize: theme.fontSize("Caption"); font.weight: theme.fontWeight("Caption"); background: Rectangle { color: theme.state.subtle; radius: 8 } }
                }
                UiButton { objectName: "errorCopyReport"; text: i18n.messages["error.copy_report"]; appearance: "quiet"; visible: popup.detailsOpen; onClicked: popup.session.copyReport() }
            }
            ColumnLayout {
                Layout.fillWidth: true; visible: popup.s.kind === "update"; spacing: 12
                UiText { objectName: "updateVersions"; Layout.fillWidth: true; text: i18n.messages["update.version_comparison"].replace("{current}", popup.s.currentVersion || "").replace("{target}", popup.s.targetVersion || "").replace("{size}", popup.s.packageSize || ""); wrapMode: Text.Wrap; textFormat: Text.PlainText }
                UiCombo { objectName: "updateLanguage"; accessibleName: i18n.messages["update.notes_language"]; model: [i18n.languages[0].name, i18n.languages[2].name]; currentIndex: popup.s.language === "en" ? 1 : 0; onActivated: popup.session.setLanguage(currentIndex === 1 ? "en" : "zh-CN") }
                UiScrollView {
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
                Slider { Layout.fillWidth: true; from: 0; to: popup.s.duration || 0; value: popup.s.timestamp || 0; stepSize: 1; enabled: popup.s.controlsEnabled || false; Accessible.name: i18n.messages["cover.time"]; onMoved: popup.session.setTimestamp(value) }
                RowLayout { Layout.fillWidth: true
                    UiText { text: i18n.messages["cover.time_seconds"]; role: "Caption" }
                    UiField { Layout.fillWidth: true; text: (popup.s.timestamp || 0).toFixed(1); enabled: popup.s.controlsEnabled || false; Accessible.name: i18n.messages["cover.time_seconds"]; validator: DoubleValidator { bottom: 0; top: popup.s.duration || 0; decimals: 1; locale: "C" } onEditingFinished: if (acceptableInput) popup.session.setTimestamp(Number(text)) }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; visible: popup.s.kind === "cookie"; spacing: 10
                UiText { Layout.fillWidth: true; text: i18n.messages["cookie.profile_name_help"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiText { text: i18n.messages["cookie.source"]; role: "Caption" }
                UiCombo { objectName: "cookieSourceCombo"; Layout.fillWidth: true; model: [i18n.messages["cookie.source_browser"], i18n.messages["cookie.source_file"]]; currentIndex: popup.s.source === "file" ? 1 : 0; onActivated: popup.session.setSource(currentIndex === 1 ? "file" : "browser") }
                UiText { text: i18n.messages["cookie.profile_name"]; role: "Caption" }
                UiField { objectName: "cookieName"; Layout.fillWidth: true; text: popup.s.name || ""; onTextChanged: popup.session.setField("name", text) }
                UiText { text: i18n.messages["cookie.domain"]; role: "Caption" }
                UiField { objectName: "cookieDomain"; Layout.fillWidth: true; text: popup.s.domain || ""; onTextChanged: popup.session.setField("domain", text); placeholderText: i18n.messages["cookie.domain_placeholder"] }
                UiCombo { objectName: "cookieBrowser"; visible: popup.s.source === "browser"; Layout.fillWidth: true; model: ["Chrome", "Edge", "Firefox", "Brave", "Opera", "Chromium"]; property var values: ["chrome", "edge", "firefox", "brave", "opera", "chromium"]; currentIndex: Math.max(0, values.indexOf(popup.s.browser)); onActivated: popup.session.setField("browser", values[currentIndex]) }
                UiField { objectName: "cookieBrowserProfile"; visible: popup.s.source === "browser"; Layout.fillWidth: true; text: popup.s.browserProfile || ""; placeholderText: i18n.messages["cookie.browser_profile_optional"]; Accessible.name: i18n.messages["cookie.browser_profile"]; onTextChanged: popup.session.setField("browserProfile", text) }
                RowLayout { Layout.fillWidth: true; visible: popup.s.source === "file"
                    UiText { Layout.fillWidth: true; text: popup.s.fileLabel || i18n.messages["cookie.file_not_selected"]; role: "Caption"; elide: Text.ElideLeft }
                    UiButton { objectName: "cookieBrowse"; text: i18n.messages["common.browse"]; onClicked: popup.session.browse() }
                }
                UiText { Layout.fillWidth: true; text: popup.s.source === "file" ? i18n.messages["cookie.file_help"] : i18n.messages["cookie.browser_help"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiText { Layout.fillWidth: true; text: popup.s.message || ""; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
            }
        }
    }
    footer: Item {
        implicitHeight: actions.implicitHeight + 32
        Flow {
            id: actions
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 8
            Repeater {
                model: popup.s.kind === "error" ? (popup.s.errorActions || []) : []
                delegate: UiButton {
                    required property var modelData
                    text: modelData.label
                    appearance: modelData.primary ? "primary" : "normal"
                    onClicked: popup.session.runAction(modelData.id)
                }
            }
            UiButton { text: i18n.messages["action.retry"]; visible: popup.s.kind === "error" && (popup.s.hasRetry || false) && !(popup.s.errorActions || []).length; onClicked: popup.session.retry() }
            UiButton { text: i18n.messages["action.open_folder"]; visible: popup.s.kind === "confirm" && (popup.s.hasFolder || false); onClicked: popup.session.openFolder() }
            UiButton { text: popup.s.acceptText || ""; appearance: "danger"; visible: popup.s.kind === "confirm"; onClicked: popup.session.answer(true) }
            UiButton { text: i18n.messages["common.preview"]; visible: popup.s.kind === "cover" && !popup.s.completed; enabled: popup.s.previewEnabled || false; onClicked: popup.session.generatePreview() }
            UiButton { text: popup.s.applyText || i18n.messages["action.set_video_cover"]; appearance: "primary"; visible: popup.s.kind === "cover" && !popup.s.completed; enabled: popup.s.applyEnabled || false; onClicked: popup.session.apply() }
            UiButton { text: i18n.messages["cover.explorer_support"]; visible: popup.s.kind === "cover" && (popup.s.explorerNeedsSupport || false); onClicked: popup.session.openExplorerSupport() }
            UiButton { text: i18n.messages["update.release_notes"]; visible: popup.s.kind === "update" && (popup.s.canRelease || false); onClicked: popup.session.action("release") }
            UiButton { objectName: "updateDownload"; text: popup.s.downloadText || i18n.messages["update.download_install"]; appearance: "primary"; visible: popup.s.kind === "update" && (popup.s.canDownload || false); onClicked: popup.session.action("download") }
            UiButton { text: popup.s.cancelEnabled ? i18n.messages["update.cancel_download"] : i18n.messages["task.status.cancelling"]; enabled: popup.s.cancelEnabled || false; visible: popup.s.kind === "update" && (popup.s.canCancel || false); onClicked: popup.session.action("cancel") }
            UiButton { objectName: "updateInstall"; text: i18n.messages["update.install_restart"]; appearance: "primary"; visible: popup.s.kind === "update" && (popup.s.canInstall || false); onClicked: popup.session.action("install") }
            UiButton { objectName: "cookieTest"; text: i18n.messages["cookie.test"]; visible: popup.s.kind === "cookie"; onClicked: popup.session.test() }
            UiButton { objectName: "cookieSave"; text: i18n.messages["common.save"]; appearance: "primary"; visible: popup.s.kind === "cookie"; onClicked: popup.session.save() }
            UiButton { id: cancelAction; objectName: "dialogCancel"; text: popup.s.kind === "confirm" ? popup.s.cancelText : popup.s.kind === "update" ? popup.s.dismissText : i18n.messages["common.close"]; enabled: popup.s.closeEnabled; onClicked: popup.session.reject() }
        }
    }
}

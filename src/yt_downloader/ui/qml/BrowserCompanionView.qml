import QtQuick
import QtQuick.Layouts

UiCategoryHost {
    id: root
    objectName: "browserCompanionPanel"
    index: 2; selectedIndex: toolbox.state.category
    readonly property string selectedBrowser: browserCompanion.state.activeBrowser
    onSelectedBrowserChanged: scroll.contentY = scroll.originY
    UiScroll {
        id: scroll
        objectName: "browserCompanionScroll"
        anchors.fill: parent
        contentHeight: body.implicitHeight + 20
        ColumnLayout {
            id: body
            width: Math.min(980, scroll.width - scroll.contentInsetRight)
            spacing: 16
            RowLayout {
                Layout.fillWidth: true
                UiText { Layout.fillWidth: true; text: i18n.messages["browser.title"]; role: "SectionTitle"; wrapMode: Text.Wrap }
                UiButton { objectName: "browser-install-guide"; text: i18n.messages["browser.guide_entry"]; appearance: "quiet"; onClicked: browserCompanion.showInstallGuide() }
            }
            UiText { Layout.fillWidth: true; text: i18n.messages["browser.description"]; color: theme.state.secondary; wrapMode: Text.Wrap }
            UiText { text: i18n.messages["browser.choose_browser"]; role: "Caption" }
            Flow {
                Layout.fillWidth: true
                spacing: 10
                Repeater {
                    model: ["chrome", "edge", "firefox"]
                    delegate: UiButton {
                        required property string modelData
                        objectName: "browser-select-" + modelData
                        text: modelData === "edge" ? "Microsoft Edge" : modelData === "chrome" ? "Chrome" : "Firefox"
                        selected: root.selectedBrowser === modelData
                        onClicked: browserCompanion.selectBrowser(modelData)
                    }
                }
            }
            Repeater {
                model: ["chrome", "edge", "firefox"]
                delegate: ColumnLayout {
                    id: card
                    required property int index
                    readonly property var info: browserCompanion.state.rows[index]
                    Layout.fillWidth: true
                    visible: root.selectedBrowser === info.browser
                    spacing: 16
                    UiText { Layout.fillWidth: true; objectName: "browser-status-" + card.info.browser; text: i18n.messages[card.info.statusKey]; wrapMode: Text.Wrap; color: theme.state.secondary }
                    SettingCard {
                        Layout.fillWidth: true
                        title: i18n.messages["browser.step_connection"]
                        UiText { Layout.fillWidth: true; text: i18n.messages[card.info.hostReady ? "browser.step_done" : card.info.busy ? "browser.step_running" : card.info.configured || card.info.noticeError ? "browser.step_attention" : "browser.step_pending"]; role: "Caption"; wrapMode: Text.Wrap }
                        UiButton {
                            objectName: "browser-install-" + card.info.browser
                            text: i18n.messages[card.info.configured ? "browser.install" : "browser.start"]
                            appearance: card.info.configured ? "normal" : "primary"
                            enabled: !card.info.busy
                            onClicked: browserCompanion.perform(card.info.browser, "install")
                        }
                        BrowserOperationNotice { Layout.fillWidth: true; info: card.info; areas: ["install", "copy_build"] }
                        UiText {
                            Layout.fillWidth: true
                            visible: !card.info.bridgeExists
                            text: i18n.messages[browserCompanion.state.sourceEnvironment ? "browser.source_help" : "browser.frozen_help"]
                            wrapMode: Text.Wrap; color: theme.state.secondary; role: "Caption"
                        }
                        UiButton {
                            objectName: "browser-copy-build-" + card.info.browser
                            visible: browserCompanion.state.sourceEnvironment && !card.info.bridgeExists
                            text: i18n.messages["browser.copy_build"]
                            enabled: !card.info.busy
                            onClicked: browserCompanion.perform(card.info.browser, "copy_build")
                        }
                    }
                    SettingCard {
                        Layout.fillWidth: true
                        title: i18n.messages["browser.step_install"]
                        UiText { Layout.fillWidth: true; text: i18n.messages[card.info.connected ? "browser.step_done" : "browser.step_pending"]; role: "Caption" }
                        UiText { Layout.fillWidth: true; text: i18n.messages["browser.install_" + card.info.browser]; wrapMode: Text.Wrap }
                        UiText { Layout.fillWidth: true; text: i18n.messages["browser.portable_path"] + "\n" + card.info.folderPath; role: "Caption"; wrapMode: Text.WrapAnywhere; color: theme.state.secondary }
                        UiText { Layout.fillWidth: true; visible: card.info.extensionReload; text: i18n.messages["browser.reload_required"]; wrapMode: Text.Wrap; color: theme.state.danger }
                        UiText { Layout.fillWidth: true; visible: card.info.extensionReload && card.info.previousFolderPath.length > 0; text: i18n.messages["browser.legacy_path"] + "\n" + card.info.previousFolderPath; role: "Caption"; wrapMode: Text.WrapAnywhere; color: theme.state.secondary }
                        UiText { Layout.fillWidth: true; text: card.info.installAddress; role: "Caption"; wrapMode: Text.Wrap; color: theme.state.accent }
                        Flow {
                            Layout.fillWidth: true; spacing: 10
                            UiButton {
                                objectName: "browser-folder-" + card.info.browser
                                text: i18n.messages["browser.folder"]
                                appearance: card.info.hostReady && !card.info.connected ? "primary" : "normal"
                                enabled: !card.info.busy
                                onClicked: browserCompanion.perform(card.info.browser, "folder")
                            }
                            UiButton {
                                objectName: "browser-copy-address-" + card.info.browser
                                text: i18n.messages["browser.copy_address"]
                                enabled: !card.info.busy
                                onClicked: browserCompanion.perform(card.info.browser, "copy_address")
                            }
                        }
                        UiButton { objectName: "browser-confirm-reload-" + card.info.browser; visible: card.info.extensionReload && card.info.configured; text: i18n.messages["browser.reload_confirm"]; enabled: !card.info.busy; onClicked: browserCompanion.perform(card.info.browser, "confirm_reload") }
                        BrowserOperationNotice { Layout.fillWidth: true; info: card.info; areas: ["folder", "copy_address", "confirm_reload"] }
                    }
                    SettingCard {
                        Layout.fillWidth: true
                        title: i18n.messages["browser.step_send"]
                        UiText { Layout.fillWidth: true; text: i18n.messages[card.info.connected ? "browser.step_done" : card.info.busy && card.info.action === "test" ? "browser.step_running" : card.info.noticeError && card.info.noticeArea === "test" ? "browser.step_attention" : "browser.step_pending"]; role: "Caption" }
                        UiText { Layout.fillWidth: true; text: i18n.messages["browser.send_help"]; wrapMode: Text.Wrap }
                        UiButton {
                            objectName: "browser-test-" + card.info.browser
                            text: i18n.messages["browser.test"]
                            enabled: !card.info.busy
                            onClicked: browserCompanion.perform(card.info.browser, "test")
                        }
                        BrowserOperationNotice { Layout.fillWidth: true; info: card.info; areas: ["test"] }
                    }
                    UiDisclosure {
                        objectName: "browser-advanced-" + card.info.browser
                        Layout.fillWidth: true
                        label: i18n.messages["browser.advanced"]
                        expanded: card.info.advanced
                        onClicked: browserCompanion.toggleAdvanced(card.info.browser)
                    }
                    SettingCard {
                        Layout.fillWidth: true
                        visible: card.info.advanced
                        UiText { Layout.fillWidth: true; text: i18n.messages["browser.identity"]; role: "Caption"; wrapMode: Text.Wrap }
                        UiField { Layout.fillWidth: true; objectName: "browser-id-" + card.info.browser; text: card.info.extensionId; enabled: !card.info.busy; Accessible.name: i18n.messages["browser.identity"]; onTextEdited: browserCompanion.setIdentity(card.info.browser, text) }
                        Flow {
                            Layout.fillWidth: true; spacing: 10
                            UiButton { objectName: "browser-repair-" + card.info.browser; text: i18n.messages["browser.repair"]; enabled: !card.info.busy; onClicked: browserCompanion.perform(card.info.browser, "repair") }
                            UiButton { objectName: "browser-remove-" + card.info.browser; text: i18n.messages["browser.remove"]; appearance: "danger"; enabled: !card.info.busy; onClicked: browserCompanion.perform(card.info.browser, "remove") }
                        }
                        BrowserOperationNotice { Layout.fillWidth: true; info: card.info; areas: ["repair", "remove"] }
                        UiText { Layout.fillWidth: true; text: i18n.messages["browser.bridge_path"] + "\n" + card.info.bridgePath; role: "Caption"; wrapMode: Text.WrapAnywhere; color: theme.state.secondary }
                        UiText { Layout.fillWidth: true; text: i18n.messages["browser.manifest_path"] + "\n" + card.info.manifestPath; role: "Caption"; wrapMode: Text.WrapAnywhere; color: theme.state.secondary }
                        UiText { Layout.fillWidth: true; text: i18n.messages["browser.folder_path"] + "\n" + card.info.folderPath; role: "Caption"; wrapMode: Text.WrapAnywhere; color: theme.state.secondary }
                    }
                }
            }
        }
    }
}

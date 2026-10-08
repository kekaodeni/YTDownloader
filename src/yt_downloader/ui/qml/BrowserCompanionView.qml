import QtQuick
import QtQuick.Layouts

UiCategoryHost {
    id: root
    objectName: "browserCompanionPanel"
    index: 2; selectedIndex: toolbox.state.category
    UiScroll {
        id: scroll
        objectName: "browserCompanionScroll"
        anchors.fill: parent
        contentHeight: body.implicitHeight + 20
        ColumnLayout {
            id: body
            width: Math.min(980, scroll.width - scroll.contentInsetRight)
            spacing: 16
            UiText { Layout.fillWidth: true; text: i18n.messages["browser.title"]; role: "SectionTitle"; wrapMode: Text.Wrap }
            UiText { Layout.fillWidth: true; text: i18n.messages["browser.description"]; color: theme.state.secondary; wrapMode: Text.Wrap }
            Repeater {
                model: ["chrome", "edge", "firefox"]
                delegate: SettingCard {
                    id: card
                    required property int index
                    readonly property var info: browserCompanion.state.rows[index]
                    Layout.fillWidth: true
                    title: info.name
                    UiText { Layout.fillWidth: true; text: i18n.messages[card.info.statusKey]; wrapMode: Text.Wrap; color: theme.state.secondary }
                    UiText { Layout.fillWidth: true; text: i18n.messages["browser.identity"]; role: "Caption"; wrapMode: Text.Wrap }
                    UiField { Layout.fillWidth: true; objectName: "browser-id-" + card.info.browser; text: card.info.extensionId; Accessible.name: i18n.messages["browser.identity"]; onTextEdited: browserCompanion.setIdentity(card.info.browser, text) }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 10
                        Repeater {
                            model: ["install", "test", "repair", "remove", "folder"]
                            delegate: UiButton {
                                required property string modelData
                                objectName: "browser-" + modelData + "-" + card.info.browser
                                text: i18n.messages["browser." + modelData]
                                onClicked: browserCompanion.perform(card.info.browser, modelData)
                            }
                        }
                    }
                }
            }
            UiText { Layout.fillWidth: true; visible: browserCompanion.state.noticeKey.length > 0; text: browserCompanion.state.noticeKey ? i18n.messages[browserCompanion.state.noticeKey] : ""; wrapMode: Text.Wrap; color: theme.state.secondary }
            UiButton { objectName: "browser-help"; text: i18n.messages["browser.help"]; onClicked: browserCompanion.toggleHelp() }
            SettingCard {
                Layout.fillWidth: true; visible: browserCompanion.state.helpVisible
                UiText { Layout.fillWidth: true; text: i18n.messages["browser.install_help"]; wrapMode: Text.Wrap }
                UiText { Layout.fillWidth: true; text: i18n.messages["browser.firefox_help"]; wrapMode: Text.Wrap }
                UiText { Layout.fillWidth: true; text: i18n.messages["browser.privacy"]; role: "Caption"; wrapMode: Text.Wrap; color: theme.state.secondary }
            }
        }
    }
}

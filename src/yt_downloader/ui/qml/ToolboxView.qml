import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "toolboxPage"
    readonly property var categories: [
        {key: "toolbox.thumbnail", icon: "image"},
        {key: "toolbox.subtitles", icon: "info", filled: true}
    ]
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32; spacing: 24
        UiText { text: i18n.messages["nav.toolbox"]; role: "PageTitle" }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: root.width < 620 ? 14 : 24
            UiNavigation {
                objectName: "toolboxNavigation"; itemPrefix: "toolboxNav-"; secondary: true
                compact: root.width < 620
                Layout.preferredWidth: compact ? 52 : 180; Layout.fillHeight: true
                model: root.categories; currentIndex: toolbox.state.category
                onActivated: function(index) { toolbox.selectCategory(index) }
            }
            UiScroll {
                id: scroll
                objectName: "toolboxScroll"
                Layout.fillWidth: true; Layout.fillHeight: true
                contentHeight: body.implicitHeight + 20
                ColumnLayout {
                    id: body
                    width: Math.min(980, scroll.width - scroll.contentInsetRight)
                    spacing: 20
                    UiText { Layout.fillWidth: true; text: i18n.messages[root.categories[toolbox.state.category].key]; role: "SectionTitle"; wrapMode: Text.Wrap }
                    MediaInputBar { itemPrefix: "toolbox-"; controller: toolbox }
                    UiText { Layout.fillWidth: true; text: i18n.messages["toolbox.subtitle"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap; visible: !toolbox.state.ready }
                    SettingCard {
                        Layout.fillWidth: true; visible: toolbox.state.ready
                        UiText { Layout.fillWidth: true; text: toolbox.state.title; role: "SectionTitle"; wrapMode: Text.Wrap }
                        UiText { Layout.fillWidth: true; text: toolbox.state.meta; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                        Item {
                            Layout.fillWidth: true
                            implicitHeight: toolbox.state.category === 0 ? thumbnailBody.implicitHeight : subtitleBody.implicitHeight
                            UiCategoryHost {
                                anchors.fill: parent; backgroundColor: theme.state.surface; index: 0; selectedIndex: toolbox.state.category; current: toolbox.state.category === 0
                                ColumnLayout {
                                    id: thumbnailBody; objectName: "toolbox-thumbnailPanel"
                                    width: parent.width; spacing: 14
                                    Thumbnail { Layout.fillWidth: true; Layout.preferredHeight: Math.min(width * 9 / 16, 280); source: toolbox.state.thumbnail; imageFillMode: Image.PreserveAspectFit }
                                    UiCombo { objectName: "toolbox-thumbnailChoice"; Layout.fillWidth: true; model: toolbox.state.thumbnailChoices.map(function(row) { return row.label }); currentIndex: toolbox.state.thumbnailIndex; enabled: !toolbox.state.toolBusy && count > 0; accessibleName: i18n.messages["toolbox.best_thumbnail"]; onActivated: toolbox.selectThumbnail(currentIndex) }
                                    UiText { Layout.fillWidth: true; visible: toolbox.state.thumbnailChoices.length === 0; text: i18n.messages["thumbnail.none"]; wrapMode: Text.Wrap; color: theme.state.secondary }
                                }
                            }
                            UiCategoryHost {
                                anchors.fill: parent; backgroundColor: theme.state.surface; index: 1; selectedIndex: toolbox.state.category; current: toolbox.state.category === 1
                                ColumnLayout {
                                    id: subtitleBody; objectName: "toolbox-subtitlePanel"
                                    width: parent.width; spacing: 12
                                    UiText { Layout.fillWidth: true; text: i18n.messages["toolbox.manual_priority"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                                    UiSwitch {
                                        objectName: "toolbox-includeAuto"; Layout.fillWidth: true
                                        text: i18n.messages["download.auto_subtitles"]; enabled: !toolbox.state.toolBusy; checked: toolbox.state.includeAuto
                                        implicitHeight: Math.max(36, implicitContentHeight)
                                        contentItem: UiText { text: parent.text; leftPadding: 54; wrapMode: Text.Wrap; color: parent.enabled ? theme.state.text : theme.state.disabled }
                                        onToggled: toolbox.setIncludeAuto(checked)
                                    }
                                    ListView {
                                        objectName: "toolbox-subtitleList"
                                        Layout.fillWidth: true; Layout.preferredHeight: Math.min(count * 46, 260)
                                        model: toolbox.subtitleEntries; reuseItems: true; clip: true
                                        boundsBehavior: Flickable.StopAtBounds
                                        ScrollBar.vertical: UiScrollBar {}
                                        delegate: CheckBox {
                                            id: subtitleChoice
                                            required property var item
                                            objectName: "toolbox-subtitle-" + item.code
                                            width: ListView.view.width - 20; height: 46
                                            text: item.name + " · " + i18n.messages[item.auto ? "toolbox.auto" : "toolbox.manual"]
                                            enabled: !toolbox.state.toolBusy; checked: item.selected
                                            spacing: 8; padding: 0
                                            indicator: Rectangle {
                                                x: 0; y: (subtitleChoice.height - height) / 2
                                                width: 20; height: 20; radius: 4
                                                color: subtitleChoice.checked ? theme.state.accent : subtitleChoice.hovered ? theme.state.subtle : theme.state.surface
                                                border.width: subtitleChoice.visualFocus ? 2 : 1
                                                border.color: subtitleChoice.checked || subtitleChoice.visualFocus ? theme.state.accent : theme.state.stroke
                                                Text { anchors.centerIn: parent; text: "✓"; font.pixelSize: 14; font.bold: true; color: theme.state.onAccent; visible: subtitleChoice.checked }
                                                Behavior on color { ColorAnimation { duration: motion.micro } }
                                            }
                                            contentItem: UiText { text: subtitleChoice.text; leftPadding: 28; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; color: subtitleChoice.enabled ? theme.state.text : theme.state.disabled }
                                            onClicked: toolbox.selectToolSubtitle(item.code, !item.selected)
                                        }
                                    }
                                    UiText { Layout.fillWidth: true; visible: toolbox.state.toolSubtitleChoices.length === 0; text: i18n.messages["download.no_subtitles"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                                    UiCombo { objectName: "toolbox-subtitleFormat"; Layout.fillWidth: true; model: ["SRT", "VTT", "ASS"]; accessibleName: i18n.messages["download.subtitle_format"]; currentIndex: ["srt", "vtt", "ass"].indexOf(toolbox.state.toolSubtitleFormat); enabled: !toolbox.state.toolBusy; onActivated: toolbox.setToolSubtitleFormat(["srt", "vtt", "ass"][currentIndex]) }
                                }
                            }
                        }
                        UiText { text: i18n.messages["download.save_location"]; wrapMode: Text.Wrap }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            UiField { Layout.fillWidth: true; text: toolbox.state.directory; enabled: !toolbox.state.toolBusy; Accessible.name: i18n.messages["download.save_location"]; onTextChanged: toolbox.setField("directory", text) }
                            UiButton { text: i18n.messages["common.browse"]; enabled: !toolbox.state.toolBusy; onClicked: toolbox.browse_requested() }
                        }
                        UiProgress { Layout.fillWidth: true; visible: toolbox.state.toolBusy; indeterminate: true }
                        UiButton {
                            objectName: "toolbox-action"; appearance: "primary"
                            text: toolbox.state.toolBusy ? i18n.messages["common.cancel"] : i18n.messages[root.categories[toolbox.state.category].key]
                            enabled: toolbox.state.toolBusy || (!toolbox.state.busy && (toolbox.state.category === 0 ? toolbox.state.thumbnailChoices.length > 0 : toolbox.state.toolSubtitleLanguages.length > 0))
                            onClicked: toolbox.requestTool()
                        }
                    }
                    SettingCard {
                        Layout.fillWidth: true; visible: toolbox.state.resultFiles.length > 0
                        title: toolbox.state.toolStatus
                        Repeater { model: toolbox.state.resultFiles
                            delegate: RowLayout {
                                required property string modelData; required property int index
                                Layout.fillWidth: true
                                UiText { Layout.fillWidth: true; text: modelData.split(/[\\/]/).pop(); elide: Text.ElideMiddle; role: "Caption" }
                                UiButton { text: i18n.messages["action.open_file"]; onClicked: toolbox.openResult(index) }
                            }
                        }
                        UiButton { text: i18n.messages["action.open_folder"]; onClicked: toolbox.openResultFolder() }
                    }
                }
            }
        }
    }
}

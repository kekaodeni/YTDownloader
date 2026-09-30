import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "settingsPage"
    property int category: settings.state.category
    readonly property var categories: [
        {key: "nav.download", icon: "arrow_download_regular.svg"},
        {key: "settings.account_cookie", icon: "info_regular.svg"},
        {key: "settings.network", icon: "link_regular.svg"},
        {key: "settings.appearance", icon: "image_regular.svg"},
        {key: "settings.updates", icon: "retry_regular.svg"},
        {key: "settings.tools", icon: "settings_regular.svg"}
    ]
    readonly property var activeScroll: [scroll0, scroll1, scroll2, scroll3, scroll4, scroll5][category]
    function selectCategory(index) { settings.selectCategory(index) }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.width < 620 ? 20 : 32
        spacing: 24
        UiText { text: i18n.messages["nav.settings"]; role: "PageTitle" }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: root.width < 620 ? 14 : 24
            ListView {
                id: navigation
                objectName: "settingsNavigation"
                Layout.preferredWidth: root.width < 620 ? 160 : 180
                Layout.fillHeight: true
                clip: true; spacing: 4; boundsBehavior: Flickable.StopAtBounds
                model: root.categories
                currentIndex: root.category
                activeFocusOnTab: true
                KeyNavigation.tab: root.activeScroll
                Keys.onUpPressed: root.selectCategory((root.category + 5) % 6)
                Keys.onDownPressed: root.selectCategory((root.category + 1) % 6)
                Keys.onReturnPressed: root.activeScroll.forceActiveFocus()
                delegate: ItemDelegate {
                    id: navItem
                    required property int index
                    required property var modelData
                    objectName: "settingsNav-" + index
                    width: ListView.view.width
                    height: Math.max(46, navLabel.implicitHeight + 20)
                    highlighted: root.category === index
                    Accessible.role: Accessible.PageTab
                    Accessible.name: i18n.messages[modelData.key]
                    Accessible.selected: highlighted
                    onClicked: { navigation.forceActiveFocus(); root.selectCategory(index) }
                    background: Rectangle {
                        radius: 8
                        color: navItem.highlighted ? theme.state.selection : navItem.down || navItem.hovered ? theme.state.subtle : theme.state.canvas
                        border.width: navigation.activeFocus && navItem.highlighted ? 1 : 0
                        border.color: theme.state.accent
                        Behavior on color { ColorAnimation { duration: motion.fast; easing.type: motion.easing } }
                        Rectangle { opacity: navItem.highlighted ? 1 : 0; Behavior on opacity { NumberAnimation { duration: motion.fast } } width: 3; height: 20; radius: 2; anchors.left: parent.left; anchors.leftMargin: 4; anchors.verticalCenter: parent.verticalCenter; color: theme.state.accent }
                    }
                    contentItem: RowLayout {
                        spacing: 10
                        ToolButton {
                            Layout.preferredWidth: 18; Layout.minimumWidth: 18; Layout.maximumWidth: 18
                            Layout.preferredHeight: 18; padding: 0; enabled: false
                            icon.source: assetsBase + "icons/" + navItem.modelData.icon
                            icon.width: 18; icon.height: 18
                            icon.color: navItem.highlighted ? theme.state.accent : theme.state.secondary
                            Behavior on icon.color { ColorAnimation { duration: motion.fast } }
                            background: null; Accessible.ignored: true
                        }
                        UiText { id: navLabel; Layout.fillWidth: true; text: i18n.messages[navItem.modelData.key]; wrapMode: Text.Wrap; role: "Button"; color: navItem.highlighted ? theme.state.accent : theme.state.text; Behavior on color { ColorAnimation { duration: motion.fast } } }
                    }
                }
            }
            Item { Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                UiCategoryHost {
                    objectName: "settingsHost-0"
                    anchors.fill: parent; index: 0; selectedIndex: root.category; current: root.category === 0
                    UiScroll {
                        id: scroll0
                        objectName: root.category === 0 ? "settingsScroll" : "settingsScroll-0"
                        anchors.fill: parent; activeFocusOnTab: true
                        contentHeight: body0.implicitHeight + 20
                        ColumnLayout {
                            id: body0
                            width: Math.min(980, parent.width - 12)
                            x: Math.max(0, (parent.width - 12 - width) / 2); spacing: 22
                            UiText { Layout.fillWidth: true; text: i18n.messages[root.categories[0].key]; role: "SectionTitle"; wrapMode: Text.Wrap }
                            ColumnLayout {
                                id: downloads
                                objectName: "settingsCategory-0"
                                Layout.fillWidth: true; spacing: 22
                                SettingCard {
                                    objectName: "downloadProfilesSection"; Layout.fillWidth: true; title: i18n.messages["settings.profiles"]
                                    SettingRow { objectName: "defaultProfileRow"; Layout.fillWidth: true; label: i18n.messages["settings.default_profile"]; description: i18n.messages["settings.profile_explainer"]
                                        UiCombo { objectName: "defaultDownloadProfile"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.default_profile"]
                                            model: settings.state.profileOptions.map(function(profile) { return profile.name })
                                            currentIndex: Math.max(0, settings.state.profileOptions.findIndex(function(profile) { return profile.id === settings.state.defaultProfileId }))
                                            onActivated: settings.setDefaultProfile(settings.state.profileOptions[currentIndex].id)
                                        }
                                    }
                                }
                                SettingCard { Layout.fillWidth: true; title: i18n.messages["settings.custom_profiles"]
                                    UiText { objectName: "emptyDownloadProfiles"; Layout.fillWidth: true; visible: settings.state.customProfiles.length === 0; text: i18n.messages["settings.empty_profiles"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                                    Repeater { model: settings.state.customProfiles
                                        delegate: SettingRow { required property var modelData; required property int index
                                            objectName: "customProfile-" + modelData.id; Layout.fillWidth: true; label: modelData.name; description: modelData.summary; separator: index < settings.state.customProfiles.length - 1
                                            UiButton { objectName: "editProfile-" + modelData.id; text: i18n.messages["common.edit"]; onClicked: settings.editProfile(modelData.id) }
                                            UiButton { objectName: "deleteProfile-" + modelData.id; text: i18n.messages["common.delete"]; appearance: "danger"; onClicked: settings.deleteProfile(modelData.id) }
                                        }
                                    }
                                    UiButton { objectName: "newDownloadProfile"; text: i18n.messages["settings.new_profile"]; onClicked: settings.newProfile() }
                                }
                                SettingCard { Layout.fillWidth: true; title: i18n.messages["settings.download_location"]
                                    UiText { text: i18n.messages["settings.default_folder"]; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                    RowLayout { Layout.fillWidth: true; spacing: 10
                                        UiField { objectName: "defaultDirectory"; Layout.fillWidth: true; text: settings.state.download_directory; Accessible.name: i18n.messages["settings.default_folder"]; onTextChanged: if (text !== settings.state.download_directory) settings.setSetting("download_directory", text) }
                                        UiButton { text: i18n.messages["common.browse"]; onClicked: settings.browse_requested("download_directory") }
                                    }
                                }
                                SettingCard { Layout.fillWidth: true; title: i18n.messages["settings.tasks"]
                                    SettingRow { Layout.fillWidth: true; label: i18n.messages["settings.concurrent_tasks"]; separator: true
                                        UiCombo { Layout.fillWidth: true; accessibleName: i18n.messages["settings.concurrent_tasks"]; model: ["1", i18n.messages["settings.concurrent_default"], "3", "4"]; currentIndex: settings.state.max_concurrent_downloads - 1; onActivated: settings.setSetting("max_concurrent_downloads", currentIndex + 1) }
                                    }
                                    SettingRow { Layout.fillWidth: true; label: i18n.messages["settings.fragment_count"]
                                        UiCombo { Layout.fillWidth: true; accessibleName: i18n.messages["settings.fragment_count"]; model: [i18n.messages["settings.fragments_auto"], "1", "2", "4", "8"]; property var values: [0,1,2,4,8]; currentIndex: Math.max(0, values.indexOf(settings.state.concurrent_fragments)); onActivated: settings.setSetting("concurrent_fragments", values[currentIndex]) }
                                    }
                                }
                            }
                        }
                    }
                }
                UiCategoryHost {
                    objectName: "settingsHost-1"
                    anchors.fill: parent; index: 1; selectedIndex: root.category; current: root.category === 1
                    UiScroll {
                        id: scroll1
                        objectName: root.category === 1 ? "settingsScroll" : "settingsScroll-1"
                        anchors.fill: parent; activeFocusOnTab: true
                        contentHeight: body1.implicitHeight + 20
                        ColumnLayout {
                            id: body1
                            width: Math.min(980, parent.width - 12)
                            x: Math.max(0, (parent.width - 12 - width) / 2); spacing: 22
                            UiText { Layout.fillWidth: true; text: i18n.messages[root.categories[1].key]; role: "SectionTitle"; wrapMode: Text.Wrap }
                            ColumnLayout { objectName: "settingsCategory-1"; Layout.fillWidth: true; spacing: 22
                                SettingCard { Layout.fillWidth: true
                                    UiText { Layout.fillWidth: true; text: i18n.messages["settings.cookie_explainer"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                                    UiButton { id: privacyHelp; objectName: "cookiePrivacyHelp"; Layout.maximumWidth: parent.width
                                        text: i18n.messages["settings.cookie_privacy"]; implicitHeight: Math.max(38, implicitContentHeight + 16)
                                        contentItem: UiText { text: privacyHelp.text; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; color: privacyHelp.palette.buttonText }
                                        onClicked: dialogs.info(i18n.messages["cookie.privacy_title"], i18n.messages["cookie.privacy_body"])
                                    }
                                }
                                SettingCard { objectName: "cookieProfiles"; Layout.fillWidth: true; title: i18n.messages["settings.saved_cookies"]
                                    UiText { Layout.fillWidth: true; text: i18n.messages["common.none_configured"]; visible: cookies.state.profileCards.length === 0; role: "Caption"; color: theme.state.secondary }
                                    Repeater { model: cookies.state.profileCards
                                        delegate: SettingRow { required property var modelData; required property int index
                                            objectName: "cookieProfile-" + modelData.id; Layout.fillWidth: true; label: modelData.name; description: modelData.summary; separator: index < cookies.state.profileCards.length - 1
                                            UiButton { objectName: "cookieEdit-" + modelData.id; text: i18n.messages["common.edit"]; onClicked: cookies.editProfile(index) }
                                            UiButton { objectName: "cookieDelete-" + modelData.id; text: i18n.messages["common.delete"]; appearance: "danger"; onClicked: cookies.requestDelete(index) }
                                        }
                                    }
                                    UiButton { objectName: "newCookieProfile"; text: i18n.messages["settings.cookie_new"]; onClicked: cookies.newProfile() }
                                    UiText { objectName: "cookieFeedback"; Layout.fillWidth: true; visible: text.length > 0; text: i18n.sourceText(cookies.state.message); role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                                    UiButton { text: i18n.messages["settings.return_reparse"]; visible: cookies.state.authRequired; onClicked: { shell._select_page(0); download.requestParse() } }
                                }
                            }
                        }
                    }
                }
                UiCategoryHost {
                    objectName: "settingsHost-2"
                    anchors.fill: parent; index: 2; selectedIndex: root.category; current: root.category === 2
                    UiScroll {
                        id: scroll2
                        objectName: root.category === 2 ? "settingsScroll" : "settingsScroll-2"
                        anchors.fill: parent; activeFocusOnTab: true
                        contentHeight: body2.implicitHeight + 20
                        ColumnLayout {
                            id: body2
                            width: Math.min(980, parent.width - 12)
                            x: Math.max(0, (parent.width - 12 - width) / 2); spacing: 22
                            UiText { Layout.fillWidth: true; text: i18n.messages[root.categories[2].key]; role: "SectionTitle"; wrapMode: Text.Wrap }
                            ColumnLayout { objectName: "settingsCategory-2"; Layout.fillWidth: true; spacing: 22
                                SettingCard { Layout.fillWidth: true; title: i18n.messages["settings.network_connection"]
                                    SettingRow { Layout.fillWidth: true; label: i18n.messages["settings.proxy_mode"]
                                        UiCombo { objectName: "proxyMode"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.proxy_mode"]; model: [i18n.messages["settings.proxy_system"], i18n.messages["settings.proxy_direct"], i18n.messages["settings.proxy_custom"]]; property var values: ["system", "direct", "custom"]; currentIndex: Math.max(0, values.indexOf(settings.state.proxy_mode)); onActivated: settings.setSetting("proxy_mode", values[currentIndex]) }
                                    }
                                    ColumnLayout { Layout.fillWidth: true; visible: settings.state.proxy_mode === "custom"; spacing: 8
                                        UiText { Layout.fillWidth: true; text: i18n.messages["settings.proxy_address"]; wrapMode: Text.Wrap }
                                        UiField { objectName: "proxyInput"; Layout.fillWidth: true; text: settings.state.custom_proxy_url; placeholderText: i18n.messages["settings.proxy_placeholder"]; Accessible.name: i18n.messages["settings.proxy_address"]; onTextChanged: if (text !== settings.state.custom_proxy_url) settings.setSetting("custom_proxy_url", text) }
                                        UiText { Layout.fillWidth: true; text: i18n.messages["settings.proxy_description"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                                    }
                                    UiButton { objectName: "testNetwork"; text: settings.state.networkBusy ? i18n.messages["settings.testing"] : i18n.messages["settings.test_connection"]; enabled: !settings.state.networkBusy; onClicked: settings.testNetwork() }
                                    UiText { objectName: "networkFeedback"; Layout.fillWidth: true; visible: text.length > 0; text: i18n.sourceText(settings.state.networkText); color: settings.state.networkSuccess ? theme.state.success : theme.state.secondary; role: "Caption"; wrapMode: Text.Wrap }
                                }
                            }
                        }
                    }
                }
                UiCategoryHost {
                    objectName: "settingsHost-3"
                    anchors.fill: parent; index: 3; selectedIndex: root.category; current: root.category === 3
                    UiScroll {
                        id: scroll3
                        objectName: root.category === 3 ? "settingsScroll" : "settingsScroll-3"
                        anchors.fill: parent; activeFocusOnTab: true
                        contentHeight: body3.implicitHeight + 20
                        ColumnLayout {
                            id: body3
                            width: Math.min(980, parent.width - 12)
                            x: Math.max(0, (parent.width - 12 - width) / 2); spacing: 22
                            UiText { Layout.fillWidth: true; text: i18n.messages[root.categories[3].key]; role: "SectionTitle"; wrapMode: Text.Wrap }
                            ColumnLayout { objectName: "settingsCategory-3"; Layout.fillWidth: true; spacing: 22
                                SettingCard { Layout.fillWidth: true
                                    SettingRow { objectName: "languageField"; Layout.fillWidth: true; label: i18n.messages["settings.language"]; separator: true
                                        UiCombo { objectName: "languageCombo"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.language"]; model: i18n.languages.map(function(language) { return language.name }); currentIndex: Math.max(0, i18n.languages.findIndex(function(language) { return language.locale === settings.state.language })); onActivated: settings.setSetting("language", i18n.languages[currentIndex].locale) }
                                    }
                                    SettingRow { Layout.fillWidth: true; label: i18n.messages["settings.theme"]; separator: true
                                        UiCombo { objectName: "themeCombo"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.theme"]; model: [i18n.messages["settings.theme_system"], i18n.messages["settings.theme_light"], i18n.messages["settings.theme_dark"]]; property var values: ["system", "light", "dark"]; currentIndex: Math.max(0, values.indexOf(settings.state.theme)); onActivated: settings.setSetting("theme", values[currentIndex]) }
                                    }
                                    SettingRow { Layout.fillWidth: true; label: i18n.messages["settings.reduce_motion"]; controlWidth: 52
                                        UiSwitch { objectName: "reduceMotion"; text: ""; Accessible.name: i18n.messages["settings.reduce_motion"]; checked: settings.state.reduce_motion; onToggled: settings.setSetting("reduce_motion", checked) }
                                    }
                                }
                            }
                        }
                    }
                }
                UiCategoryHost {
                    objectName: "settingsHost-4"
                    anchors.fill: parent; index: 4; selectedIndex: root.category; current: root.category === 4
                    UiScroll {
                        id: scroll4
                        objectName: root.category === 4 ? "settingsScroll" : "settingsScroll-4"
                        anchors.fill: parent; activeFocusOnTab: true
                        contentHeight: body4.implicitHeight + 20
                        ColumnLayout {
                            id: body4
                            width: Math.min(980, parent.width - 12)
                            x: Math.max(0, (parent.width - 12 - width) / 2); spacing: 22
                            UiText { Layout.fillWidth: true; text: i18n.messages[root.categories[4].key]; role: "SectionTitle"; wrapMode: Text.Wrap }
                            ColumnLayout { objectName: "settingsCategory-4"; Layout.fillWidth: true; spacing: 22
                                SettingCard { Layout.fillWidth: true
                                    SettingRow { Layout.fillWidth: true; label: i18n.messages["settings.stable_channel"]; controlWidth: 0 }
                                    SettingRow { Layout.fillWidth: true; label: i18n.messages["settings.auto_updates"]; controlWidth: 52
                                        UiSwitch { objectName: "autoCheckUpdates"; text: ""; Accessible.name: i18n.messages["settings.auto_updates"]; checked: settings.state.auto_check_updates; onToggled: settings.setSetting("auto_check_updates", checked) }
                                    }
                                }
                            }
                        }
                    }
                }
                UiCategoryHost {
                    objectName: "settingsHost-5"
                    anchors.fill: parent; index: 5; selectedIndex: root.category; current: root.category === 5
                    UiScroll {
                        id: scroll5
                        objectName: root.category === 5 ? "settingsScroll" : "settingsScroll-5"
                        anchors.fill: parent; activeFocusOnTab: true
                        contentHeight: body5.implicitHeight + 20
                        ColumnLayout {
                            id: body5
                            width: Math.min(980, parent.width - 12)
                            x: Math.max(0, (parent.width - 12 - width) / 2); spacing: 22
                            UiText { Layout.fillWidth: true; text: i18n.messages[root.categories[5].key]; role: "SectionTitle"; wrapMode: Text.Wrap }
                            ColumnLayout { objectName: "settingsCategory-5"; Layout.fillWidth: true; spacing: 22
                                SettingCard { Layout.fillWidth: true; title: i18n.messages["settings.component_versions"]
                                    SettingRow { Layout.fillWidth: true; label: "yt-dlp"; separator: true; controlWidth: 160; UiText { text: settings.state.ytdlpVersion } }
                                    SettingRow { Layout.fillWidth: true; label: "FFmpeg"; controlWidth: 240; UiText { Layout.fillWidth: true; text: settings.state.ffmpegVersion || i18n.messages["settings.ffmpeg_unavailable"]; wrapMode: Text.WrapAnywhere } }
                                }
                                SettingCard { Layout.fillWidth: true; title: "FFmpeg"
                                    SettingRow { Layout.fillWidth: true; label: settings.state.ffmpeg_directory ? i18n.messages["settings.ffmpeg_custom"] : i18n.messages["settings.ffmpeg_builtin"]; description: settings.state.ffmpegPath
                                        UiButton { objectName: "changeFfmpeg"; Layout.fillWidth: true; text: i18n.messages["settings.ffmpeg_use_custom"]; onClicked: settings.browse_requested("ffmpeg_directory") }
                                    }
                                    UiButton { objectName: "restoreFfmpeg"; visible: settings.state.ffmpeg_directory.length > 0; text: i18n.messages["settings.ffmpeg_restore_builtin"]; onClicked: settings.setSetting("ffmpeg_directory", "") }
                                }
                                SettingCard { Layout.fillWidth: true; title: i18n.messages["settings.diagnostics"]
                                    Flow { Layout.fillWidth: true; spacing: 10
                                        UiButton { objectName: "openLogs"; text: i18n.messages["settings.logs"]; onClicked: settings.open_logs_requested() }
                                        UiButton { objectName: "copySystemInfo"; text: i18n.messages["settings.copy_system"]; onClicked: settings.copy_system_info_requested() }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: saveRow.implicitHeight + 20
            visible: settings.state.saveVisible; color: theme.state.surface; radius: 10; border.color: theme.state.stroke
            RowLayout { id: saveRow; anchors.fill: parent; anchors.margins: 10
                UiText { objectName: "saveFeedback"; Layout.fillWidth: true; text: i18n.sourceText(settings.state.saveText); role: "Caption"; wrapMode: Text.Wrap }
                UiButton { text: i18n.messages["settings.save_now"]; onClicked: settings.save() }
            }
        }
    }
    Dialog {
        id: profileEditor
        objectName: "downloadProfileEditor"
        property int surfaceRadius: 16
        parent: Overlay.overlay; modal: true; focus: true; closePolicy: Popup.NoAutoClose
        width: Math.min(560, parent ? parent.width - 32 : 560)
        height: Math.min(720, parent ? parent.height - 36 : 720)
        x: parent ? (parent.width - width) / 2 : 0
        y: parent ? (parent.height - height) / 2 : 0
        padding: 0
        title: ""
        background: Rectangle {
            objectName: "profileEditorSurface"
            radius: profileEditor.surfaceRadius
            color: theme.state.elevated
            border.color: theme.state.stroke
        }
        Overlay.modal: UiDimmer { }
        enter: UiPopupEnter { duration: motion.standard }
        exit: UiPopupExit { }
        onRejected: settings.closeProfileEditor()
        onClosed: if (settings.state.profileEditorOpen) settings.closeProfileEditor()
        Connections {
            target: settings
            function onChanged() {
                if (settings.state.profileEditorOpen && !profileEditor.visible) profileEditor.open()
                else if (!settings.state.profileEditorOpen && profileEditor.visible) profileEditor.close()
            }
        }
        contentItem: ColumnLayout {
            spacing: 0
            Item {
                objectName: "profileEditorHeader"
                Layout.fillWidth: true
                Layout.preferredHeight: 66
                UiText {
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.leftMargin: 24; anchors.rightMargin: 24
                    anchors.verticalCenter: parent.verticalCenter
                    text: i18n.messages["settings.custom_profile_editor"]; role: "SectionTitle"
                }
            }
            ScrollView {
                id: profileEditorBody
                objectName: "profileEditorBody"
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.leftMargin: 24; Layout.rightMargin: 24
                clip: true; contentWidth: availableWidth
                ColumnLayout { width: profileEditorBody.availableWidth; spacing: 14
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.name"]
                    UiField { objectName: "profileNameInput"; Layout.fillWidth: true; text: settings.state.profileDraftName; placeholderText: i18n.messages["settings.profile_name_placeholder"]; onTextEdited: settings.editProfileField("name", text) }
                }
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.download_content"]
                    UiCombo { objectName: "profileContentMode"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.download_content"]; model: [i18n.messages["settings.content_video_audio"], i18n.messages["settings.content_video"], i18n.messages["settings.content_audio"]]; property var values: ["video_audio", "video_only", "audio_only"]; currentIndex: values.indexOf(settings.state.profileDraftContentMode); onActivated: settings.editProfileField("content_mode", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: i18n.messages["download.quality"]
                    UiCombo { objectName: "profileQuality"; Layout.fillWidth: true; accessibleName: i18n.messages["download.quality"]; model: [i18n.messages["settings.quality_recommended"], i18n.messages["settings.quality_highest"], "2160p", "1440p", "1080p", "720p"]; property var values: ["recommended", "highest", "2160p", "1440p", "1080p", "720p"]; currentIndex: values.indexOf(settings.state.profileDraftQuality); onActivated: settings.editProfileField("quality_tier", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.video_codec"]
                    UiCombo { objectName: "profileCodec"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.video_codec"]; model: [i18n.messages["settings.codec_auto"], "AV1", "VP9", "H.264"]; property var values: ["auto", "av1", "vp9", "h264"]; currentIndex: values.indexOf(settings.state.profileDraftCodec); onActivated: settings.editProfileField("codec_preference", values[currentIndex]) }
                }
                GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 12; rowSpacing: 0
                    SettingField { Layout.fillWidth: true; label: i18n.messages["settings.audio_format"]
                        UiCombo { objectName: "profileAudioCodec"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.audio_format"]; model: [i18n.messages["settings.audio_original"], "M4A", "MP3", "Opus", "FLAC"]; property var values: ["original", "m4a", "mp3", "opus", "flac"]; currentIndex: values.indexOf(settings.state.profileDraftAudioCodec); onActivated: settings.editProfileField("audio_codec", values[currentIndex]) }
                    }
                    SettingField { Layout.fillWidth: true; label: i18n.messages["settings.audio_quality"]
                        UiCombo { objectName: "profileAudioQuality"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.audio_quality"]; model: [i18n.messages["settings.audio_original_short"], "320 kbps", "256 kbps", "192 kbps", "128 kbps"]; property var values: ["original", "320", "256", "192", "128"]; currentIndex: values.indexOf(settings.state.profileDraftAudioQuality); onActivated: settings.editProfileField("audio_quality", values[currentIndex]) }
                    }
                }
                RowLayout { Layout.fillWidth: true; spacing: 20
                    UiSwitch { objectName: "profileSubtitleEnabled"; text: i18n.messages["settings.subtitle_download"]; checked: settings.state.profileDraftSubtitleEnabled; onToggled: settings.editProfileField("subtitle_enabled", checked) }
                    UiSwitch { objectName: "profileSubtitleAuto"; text: i18n.messages["settings.subtitle_auto"]; enabled: settings.state.profileDraftSubtitleEnabled; checked: settings.state.profileDraftSubtitleAuto; onToggled: settings.editProfileField("subtitle_auto", checked) }
                }
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.subtitle_format"]
                    UiCombo { objectName: "profileSubtitleFormat"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.subtitle_format"]; model: ["SRT", "VTT"]; property var values: ["srt", "vtt"]; currentIndex: values.indexOf(settings.state.profileDraftSubtitleFormat); enabled: settings.state.profileDraftSubtitleEnabled; onActivated: settings.editProfileField("subtitle_format", values[currentIndex]) }
                }
                UiSwitch { objectName: "profileSubtitleEmbed"; text: i18n.messages["settings.subtitle_embed"]; enabled: settings.state.profileDraftSubtitleEnabled; checked: settings.state.profileDraftSubtitleEmbed; onToggled: settings.editProfileField("subtitle_embed", checked) }
                UiText { objectName: "profileEditorMessage"; Layout.fillWidth: true; visible: text.length > 0; text: i18n.sourceText(settings.state.profileMessage); role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                }
            }
            RowLayout {
                objectName: "profileEditorActions"
                Layout.fillWidth: true
                Layout.leftMargin: 24; Layout.rightMargin: 24
                Layout.topMargin: 20; Layout.bottomMargin: 24
                spacing: 8
                Item { Layout.fillWidth: true }
                UiButton { objectName: "profileEditorCancel"; text: i18n.messages["common.cancel"]; onClicked: settings.closeProfileEditor() }
                UiButton { objectName: "saveProfile"; text: i18n.messages["common.save"]; appearance: "primary"; onClicked: settings.saveProfile() }
            }
        }
    }
}

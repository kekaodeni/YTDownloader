import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
Item {
    id: root
    objectName: "settingsPage"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32; spacing: 20
        UiText { text: i18n.messages["nav.settings"]; role: "PageTitle" }
        UiScroll {
            id: scroll; objectName: "settingsScroll"; Layout.fillWidth: true; Layout.fillHeight: true
            contentHeight: body.implicitHeight + 20
            ColumnLayout {
                id: body; width: scroll.width - 12; spacing: 20
                UiText { text: i18n.messages["nav.download"]; role: "SectionTitle" }
                ColumnLayout {
                    id: downloadProfilesSection; objectName: "downloadProfilesSection"
                    Layout.fillWidth: true; spacing: 10
                    UiText { text: i18n.messages["settings.profiles"]; role: "SectionTitle" }
                    SettingField { Layout.fillWidth: true; label: i18n.messages["settings.default_profile"]
                        UiCombo {
                            objectName: "defaultDownloadProfile"; Layout.fillWidth: true
                            accessibleName: i18n.messages["settings.default_profile"]
                            model: settings.state.profileOptions.map(function(profile) { return profile.name })
                            currentIndex: Math.max(0, settings.state.profileOptions.findIndex(function(profile) { return profile.id === settings.state.defaultProfileId }))
                            onActivated: settings.setDefaultProfile(settings.state.profileOptions[currentIndex].id)
                        }
                    }
                    UiText { objectName: "profileExplainer"; Layout.fillWidth: true; text: i18n.messages["settings.profile_explainer"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        UiText { Layout.fillWidth: true; text: i18n.messages["settings.custom_profiles"]; role: "SectionTitle" }
                        UiButton { objectName: "newDownloadProfile"; text: i18n.messages["settings.new_profile"]; appearance: "normal"; onClicked: settings.newProfile() }
                    }
                    UiText { objectName: "emptyDownloadProfiles"; Layout.fillWidth: true; visible: settings.state.customProfiles.length === 0; text: i18n.messages["settings.empty_profiles"]; role: "Caption"; color: theme.state.muted }
                    Repeater {
                        model: settings.state.customProfiles
                        delegate: Rectangle {
                            required property var modelData
                            objectName: "customProfile-" + modelData.id
                            Layout.fillWidth: true; implicitHeight: 68; radius: 10
                            color: theme.state.surface; border.color: theme.state.stroke
                            RowLayout { anchors.fill: parent; anchors.margins: 10; spacing: 8
                                ColumnLayout { Layout.fillWidth: true; spacing: 2
                                    UiText { Layout.fillWidth: true; text: modelData.name; elide: Text.ElideRight }
                                    UiText { Layout.fillWidth: true; text: modelData.summary; role: "Caption"; color: theme.state.secondary; elide: Text.ElideRight }
                                }
                                UiButton { objectName: "editProfile-" + modelData.id; text: i18n.messages["common.edit"]; onClicked: settings.editProfile(modelData.id) }
                                UiButton { objectName: "deleteProfile-" + modelData.id; text: i18n.messages["action.delete_record"]; appearance: "danger"; onClicked: settings.deleteProfile(modelData.id) }
                            }
                        }
                    }
                }
                SettingField {
                    Layout.fillWidth: true; label: i18n.messages["settings.default_folder"]
                    RowLayout { Layout.fillWidth: true
                        UiField { objectName: "defaultDirectory"; Layout.fillWidth: true; text: settings.state.download_directory; Accessible.name: i18n.messages["settings.default_folder"]; onTextChanged: if (text !== settings.state.download_directory) settings.setSetting("download_directory", text) }
                        UiButton { text: i18n.messages["common.browse"]; onClicked: settings.browse_requested("download_directory") }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: root.width >= 720 ? 2 : 1; columnSpacing: 16; rowSpacing: 16
                    SettingField { Layout.fillWidth: true; label: i18n.messages["settings.concurrent_tasks"]
                        UiCombo { Layout.fillWidth: true; accessibleName: i18n.messages["settings.concurrent_tasks"]; model: ["1", i18n.messages["settings.concurrent_default"], "3", "4"]; currentIndex: settings.state.max_concurrent_downloads - 1; onActivated: settings.setSetting("max_concurrent_downloads", currentIndex + 1) }
                    }
                    SettingField { Layout.fillWidth: true; label: i18n.messages["settings.fragment_count"]
                        UiCombo { Layout.fillWidth: true; accessibleName: i18n.messages["settings.fragment_count"]; model: [i18n.messages["settings.fragments_auto"], "1", "2", "4", "8"]; property var values: [0,1,2,4,8]; currentIndex: Math.max(0, values.indexOf(settings.state.concurrent_fragments)); onActivated: settings.setSetting("concurrent_fragments", values[currentIndex]) }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: i18n.messages["settings.account_cookie"]; role: "SectionTitle" }
                UiText { Layout.fillWidth: true; text: i18n.messages["settings.cookie_explainer"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiButton { objectName: "cookiePrivacyHelp"; text: i18n.messages["settings.cookie_privacy"]; icon.source: assetsBase + "icons/info_regular.svg"; appearance: "normal"; onClicked: dialogs.info(i18n.messages["cookie.privacy_title"], i18n.messages["cookie.privacy_body"]) }
                UiText { text: i18n.messages["settings.saved_cookies"]; role: "SectionTitle" }
                UiText { Layout.fillWidth: true; text: i18n.messages["common.none_configured"]; visible: cookies.state.profileCards.length === 0; role: "Caption"; color: theme.state.secondary }
                Flow { objectName: "cookieProfiles"; Layout.fillWidth: true; spacing: 10
                    Repeater { model: cookies.state.profileCards
                        delegate: Rectangle { required property var modelData; required property int index
                            objectName: "cookieProfile-" + modelData.id; width: Math.max(240, Math.min(420, body.width - 20)); height: 64; radius: 10; color: theme.state.surface; border.color: theme.state.stroke
                            RowLayout { anchors.fill: parent; anchors.margins: 10; spacing: 8
                                ColumnLayout { Layout.fillWidth: true; spacing: 1
                                    UiText { Layout.fillWidth: true; text: modelData.name; elide: Text.ElideRight }
                                    UiText { Layout.fillWidth: true; text: modelData.summary; role: "Caption"; color: theme.state.secondary; elide: Text.ElideRight }
                                }
                                UiButton { objectName: "cookieEdit-" + modelData.id; text: i18n.messages["common.edit"]; onClicked: cookies.editProfile(index) }
                                UiButton { objectName: "cookieDelete-" + modelData.id; text: i18n.messages["action.delete_record"]; appearance: "danger"; onClicked: cookies.requestDelete(index) }
                            }
                        }
                    }
                }
                UiButton { objectName: "newCookieProfile"; text: i18n.messages["settings.cookie_new"]; onClicked: cookies.newProfile() }
                UiText { objectName: "cookieFeedback"; Layout.fillWidth: true; text: i18n.sourceText(cookies.state.message); role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiButton { text: i18n.messages["settings.return_reparse"]; visible: cookies.state.authRequired; onClicked: { shell._select_page(0); download.requestParse() } }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: i18n.messages["settings.network"]; role: "SectionTitle" }
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.network_connection"]
                    UiCombo { Layout.fillWidth: true; accessibleName: i18n.messages["settings.proxy_mode"]; model: [i18n.messages["settings.proxy_system"], i18n.messages["settings.proxy_direct"], i18n.messages["settings.proxy_custom"]]; property var values: ["system", "direct", "custom"]; currentIndex: Math.max(0, values.indexOf(settings.state.proxy_mode)); onActivated: settings.setSetting("proxy_mode", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.proxy_custom"]; description: i18n.messages["settings.proxy_description"]
                    UiField { objectName: "proxyInput"; Layout.fillWidth: true; enabled: settings.state.proxy_mode === "custom"; text: settings.state.custom_proxy_url; placeholderText: i18n.messages["settings.proxy_placeholder"]; Accessible.name: i18n.messages["settings.proxy_address"]; onTextChanged: settings.setSetting("custom_proxy_url", text) }
                }
                RowLayout { Layout.fillWidth: true
                    UiButton { text: settings.state.networkBusy ? i18n.messages["settings.testing"] : i18n.messages["settings.test_connection"]; enabled: !settings.state.networkBusy; onClicked: settings.testNetwork() }
                    UiText { objectName: "networkFeedback"; Layout.fillWidth: true; text: i18n.sourceText(settings.state.networkText); color: theme.state.secondary; role: "Caption"; wrapMode: Text.Wrap }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: i18n.messages["settings.appearance"]; role: "SectionTitle" }
                SettingField { objectName: "languageField"; Layout.fillWidth: true; label: i18n.messages["settings.language"]
                    UiCombo { objectName: "languageCombo"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.language"]
                        model: i18n.languages.map(function(language) { return language.name })
                        currentIndex: Math.max(0, i18n.languages.findIndex(function(language) { return language.locale === settings.state.language }))
                        onActivated: settings.setSetting("language", i18n.languages[currentIndex].locale)
                    }
                }
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.theme"]
                    UiCombo { objectName: "themeCombo"; Layout.fillWidth: true; accessibleName: i18n.messages["settings.theme"]; model: [i18n.messages["settings.theme_system"], i18n.messages["settings.theme_light"], i18n.messages["settings.theme_dark"]]; property var values: ["system", "light", "dark"]; currentIndex: Math.max(0, values.indexOf(settings.state.theme)); onActivated: settings.setSetting("theme", values[currentIndex]) }
                }
                UiSwitch { objectName: "reduceMotion"; text: i18n.messages["settings.reduce_motion"]; checked: settings.state.reduce_motion; onToggled: settings.setSetting("reduce_motion", checked) }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: i18n.messages["settings.updates"]; role: "SectionTitle" }
                UiText { text: i18n.messages["settings.stable_channel"]; role: "Secondary"; color: theme.state.secondary }
                UiSwitch { objectName: "autoCheckUpdates"; text: i18n.messages["settings.auto_updates"]; checked: settings.state.auto_check_updates; onToggled: settings.setSetting("auto_check_updates", checked) }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: i18n.messages["settings.tools"]; role: "SectionTitle" }
                UiText { Layout.fillWidth: true; text: "yt-dlp  " + settings.state.ytdlpVersion; role: "Secondary"; color: theme.state.secondary }
                UiText { Layout.fillWidth: true; text: "FFmpeg  " + (settings.state.ffmpegDescription || i18n.messages["settings.ffmpeg_unavailable"]); role: "Caption"; color: theme.state.muted; wrapMode: Text.WrapAnywhere }
                SettingField { Layout.fillWidth: true; label: i18n.messages["settings.ffmpeg_directory"]
                    RowLayout { Layout.fillWidth: true
                        UiField { Layout.fillWidth: true; text: settings.state.ffmpeg_directory; placeholderText: i18n.messages["settings.ffmpeg_placeholder"]; Accessible.name: i18n.messages["settings.ffmpeg_directory"]; onTextChanged: settings.setSetting("ffmpeg_directory", text) }
                        UiButton { text: i18n.messages["settings.repair_path"]; onClicked: settings.browse_requested("ffmpeg_directory") }
                    }
                }
                Flow { Layout.fillWidth: true; spacing: 8
                    UiButton { text: i18n.messages["settings.logs"]; onClicked: settings.open_logs_requested() }
                    UiButton { text: i18n.messages["settings.copy_system"]; onClicked: settings.copy_system_info_requested() }
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
        Overlay.modal: Rectangle { color: "#550C1524" }
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

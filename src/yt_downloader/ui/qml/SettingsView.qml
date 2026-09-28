import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
Item {
    id: root
    objectName: "settingsPage"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32; spacing: 20
        UiText { text: "设置"; role: "PageTitle" }
        UiScroll {
            id: scroll; objectName: "settingsScroll"; Layout.fillWidth: true; Layout.fillHeight: true
            contentHeight: body.implicitHeight + 20
            ColumnLayout {
                id: body; width: scroll.width - 12; spacing: 20
                UiText { text: "下载"; role: "SectionTitle" }
                ColumnLayout {
                    id: downloadProfilesSection; objectName: "downloadProfilesSection"
                    Layout.fillWidth: true; spacing: 10
                    UiText { text: "下载预设"; role: "SectionTitle" }
                    SettingField { Layout.fillWidth: true; label: "默认下载预设"
                        UiCombo {
                            objectName: "defaultDownloadProfile"; Layout.fillWidth: true
                            accessibleName: "默认下载预设"
                            model: settings.state.profileOptions.map(function(profile) { return profile.name })
                            currentIndex: Math.max(0, settings.state.profileOptions.findIndex(function(profile) { return profile.id === settings.state.defaultProfileId }))
                            onActivated: settings.setDefaultProfile(settings.state.profileOptions[currentIndex].id)
                        }
                    }
                    UiText { Layout.fillWidth: true; text: "用于设置新解析任务的初始下载参数。解析后仍可针对当前视频单独调整。"; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        UiText { Layout.fillWidth: true; text: "自定义预设"; role: "SectionTitle" }
                        UiButton { objectName: "newDownloadProfile"; text: "+ 新建预设"; appearance: "normal"; onClicked: settings.newProfile() }
                    }
                    UiText { objectName: "emptyDownloadProfiles"; Layout.fillWidth: true; visible: settings.state.customProfiles.length === 0; text: "暂无自定义预设。"; role: "Caption"; color: theme.state.muted }
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
                                UiButton { objectName: "editProfile-" + modelData.id; text: "编辑"; onClicked: settings.editProfile(modelData.id) }
                                UiButton { objectName: "deleteProfile-" + modelData.id; text: "删除"; appearance: "danger"; onClicked: settings.deleteProfile(modelData.id) }
                            }
                        }
                    }
                }
                SettingField {
                    Layout.fillWidth: true; label: "默认下载目录"
                    RowLayout { Layout.fillWidth: true
                        UiField { objectName: "defaultDirectory"; Layout.fillWidth: true; text: settings.state.download_directory; Accessible.name: "默认下载目录"; onTextChanged: settings.edit("download_directory", text) }
                        UiButton { text: "浏览"; onClicked: settings.browse_requested("download_directory") }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: root.width >= 720 ? 2 : 1; columnSpacing: 16; rowSpacing: 16
                    SettingField { Layout.fillWidth: true; label: "同时下载任务数"
                        UiCombo { Layout.fillWidth: true; accessibleName: "同时下载任务数"; model: ["1", "2（默认）", "3", "4"]; currentIndex: settings.state.max_concurrent_downloads - 1; onActivated: settings.edit("max_concurrent_downloads", currentIndex + 1) }
                    }
                    SettingField { Layout.fillWidth: true; label: "分片并发"
                        UiCombo { Layout.fillWidth: true; accessibleName: "分片并发数"; model: ["自动", "1", "2", "4", "8"]; property var values: [0,1,2,4,8]; currentIndex: Math.max(0, values.indexOf(settings.state.concurrent_fragments)); onActivated: settings.edit("concurrent_fragments", values[currentIndex]) }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: "账户与 Cookie"; role: "SectionTitle" }
                UiText { Layout.fillWidth: true; text: "需要登录的网站可保存浏览器或 cookies.txt 的来源。下载页开启“使用 Cookie”时，按链接所在网站匹配配置。"; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiButton { objectName: "cookiePrivacyHelp"; text: "查看 Cookie 用途与隐私说明"; icon.source: assetsBase + "icons/info_regular.svg"; appearance: "normal"; onClicked: dialogs.info("Cookie 的用途与隐私说明", "Cookie 可代表网站登录状态，属于敏感凭据。浏览器来源由 yt-dlp 在解析或下载时读取；cookies.txt 文件仍保留在你选择的位置。请只配置自己有权访问的网站，不要分享 Cookie 文件。关闭下载页的“使用 Cookie”后，本次任务匿名访问。") }
                UiText { text: "已保存的 Cookie 配置"; role: "SectionTitle" }
                UiText { Layout.fillWidth: true; text: "暂无配置"; visible: cookies.state.profileCards.length === 0; role: "Caption"; color: theme.state.secondary }
                Flow { objectName: "cookieProfiles"; Layout.fillWidth: true; spacing: 10
                    Repeater { model: cookies.state.profileCards
                        delegate: Rectangle { required property var modelData; required property int index
                            objectName: "cookieProfile-" + modelData.id; width: Math.max(240, Math.min(420, body.width - 20)); height: 64; radius: 10; color: theme.state.surface; border.color: theme.state.stroke
                            RowLayout { anchors.fill: parent; anchors.margins: 10; spacing: 8
                                ColumnLayout { Layout.fillWidth: true; spacing: 1
                                    UiText { Layout.fillWidth: true; text: modelData.name; elide: Text.ElideRight }
                                    UiText { Layout.fillWidth: true; text: modelData.summary; role: "Caption"; color: theme.state.secondary; elide: Text.ElideRight }
                                }
                                UiButton { objectName: "cookieEdit-" + modelData.id; text: "编辑"; onClicked: cookies.editProfile(index) }
                                UiButton { objectName: "cookieDelete-" + modelData.id; text: "删除"; appearance: "danger"; onClicked: cookies.requestDelete(index) }
                            }
                        }
                    }
                }
                UiButton { objectName: "newCookieProfile"; text: "+ 新建 Cookie 配置"; onClicked: cookies.newProfile() }
                UiText { Layout.fillWidth: true; text: cookies.state.message; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                UiButton { text: "返回并重新解析"; visible: cookies.state.authRequired; onClicked: { shell._select_page(0); download.requestParse() } }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: "网络"; role: "SectionTitle" }
                SettingField { Layout.fillWidth: true; label: "网络连接"
                    UiCombo { Layout.fillWidth: true; accessibleName: "网络代理模式"; model: ["系统代理", "直连", "自定义代理"]; property var values: ["system", "direct", "custom"]; currentIndex: Math.max(0, values.indexOf(settings.state.proxy_mode)); onActivated: settings.edit("proxy_mode", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: "自定义代理"; description: "支持 HTTP、HTTPS、SOCKS4、SOCKS5 和 SOCKS5H。"
                    UiField { objectName: "proxyInput"; Layout.fillWidth: true; enabled: settings.state.proxy_mode === "custom"; text: settings.state.custom_proxy_url; placeholderText: "例如 http://127.0.0.1:8080"; Accessible.name: "自定义代理地址"; onTextChanged: settings.edit("custom_proxy_url", text) }
                }
                RowLayout { Layout.fillWidth: true
                    UiButton { text: settings.state.networkBusy ? "正在测试…" : "测试连接"; enabled: !settings.state.networkBusy; onClicked: settings.testNetwork() }
                    UiText { Layout.fillWidth: true; text: settings.state.networkText; color: theme.state.secondary; role: "Caption"; wrapMode: Text.Wrap }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: "外观"; role: "SectionTitle" }
                SettingField { Layout.fillWidth: true; label: "主题"
                    UiCombo { objectName: "themeCombo"; Layout.fillWidth: true; accessibleName: "界面主题"; model: ["跟随系统", "浅色", "深色"]; property var values: ["system", "light", "dark"]; currentIndex: Math.max(0, values.indexOf(settings.state.theme)); onActivated: settings.edit("theme", values[currentIndex]) }
                }
                UiSwitch { objectName: "reduceMotion"; text: "减少界面动态效果"; checked: settings.state.reduce_motion; onToggled: settings.edit("reduce_motion", checked) }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: "更新"; role: "SectionTitle" }
                UiText { text: "稳定通道"; role: "Secondary"; color: theme.state.secondary }
                UiSwitch { objectName: "autoCheckUpdates"; text: "自动检查更新"; checked: settings.state.auto_check_updates; onToggled: settings.edit("auto_check_updates", checked) }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
                UiText { text: "工具与诊断"; role: "SectionTitle" }
                UiText { Layout.fillWidth: true; text: "yt-dlp  " + settings.state.ytdlpVersion; role: "Secondary"; color: theme.state.secondary }
                UiText { Layout.fillWidth: true; text: "FFmpeg  " + settings.state.ffmpegDescription; role: "Caption"; color: theme.state.muted; wrapMode: Text.WrapAnywhere }
                SettingField { Layout.fillWidth: true; label: "FFmpeg 目录"
                    RowLayout { Layout.fillWidth: true
                        UiField { Layout.fillWidth: true; text: settings.state.ffmpeg_directory; placeholderText: "留空时使用随软件分发的 FFmpeg"; Accessible.name: "FFmpeg 目录"; onTextChanged: settings.edit("ffmpeg_directory", text) }
                        UiButton { text: "修复路径"; onClicked: settings.browse_requested("ffmpeg_directory") }
                    }
                }
                Flow { Layout.fillWidth: true; spacing: 8
                    UiButton { text: "打开日志目录"; onClicked: settings.open_logs_requested() }
                    UiButton { text: "复制系统信息"; onClicked: settings.copy_system_info_requested() }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: saveRow.implicitHeight + 20
            visible: settings.state.saveVisible; color: theme.state.surface; radius: 10; border.color: theme.state.stroke
            RowLayout { id: saveRow; anchors.fill: parent; anchors.margins: 10
                UiText { Layout.fillWidth: true; text: settings.state.saveText; role: "Caption"; wrapMode: Text.Wrap }
                UiButton { text: "立即保存"; onClicked: settings.save() }
            }
        }
    }
    Dialog {
        id: profileEditor
        objectName: "downloadProfileEditor"
        parent: Overlay.overlay; modal: true; focus: true; closePolicy: Popup.NoAutoClose
        width: Math.min(560, parent ? parent.width - 32 : 560)
        height: Math.min(680, parent ? parent.height - 36 : 680)
        x: parent ? (parent.width - width) / 2 : 0
        y: parent ? (parent.height - height) / 2 : 0
        padding: 22
        title: "自定义下载预设"
        background: Rectangle { radius: 16; color: theme.state.elevated; border.color: theme.state.stroke }
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
        contentItem: ScrollView {
            clip: true; contentWidth: availableWidth
            ColumnLayout { width: parent.width; spacing: 14
                SettingField { Layout.fillWidth: true; label: "名称"
                    UiField { objectName: "profileNameInput"; Layout.fillWidth: true; text: settings.state.profileDraftName; placeholderText: "例如：2160p 下载"; onTextEdited: settings.editProfileField("name", text) }
                }
                SettingField { Layout.fillWidth: true; label: "下载内容"
                    UiCombo { objectName: "profileContentMode"; Layout.fillWidth: true; accessibleName: "预设下载内容"; model: ["视频 + 音频", "仅视频", "仅音频"]; property var values: ["video_audio", "video_only", "audio_only"]; currentIndex: values.indexOf(settings.state.profileDraftContentMode); onActivated: settings.editProfileField("content_mode", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: "画质"
                    UiCombo { objectName: "profileQuality"; Layout.fillWidth: true; accessibleName: "预设画质"; model: ["自动推荐", "最高质量", "2160p", "1440p", "1080p", "720p"]; property var values: ["recommended", "highest", "2160p", "1440p", "1080p", "720p"]; currentIndex: values.indexOf(settings.state.profileDraftQuality); onActivated: settings.editProfileField("quality_tier", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: "视频编码"
                    UiCombo { objectName: "profileCodec"; Layout.fillWidth: true; accessibleName: "预设视频编码"; model: ["自动推荐", "AV1", "VP9", "H.264"]; property var values: ["auto", "av1", "vp9", "h264"]; currentIndex: values.indexOf(settings.state.profileDraftCodec); onActivated: settings.editProfileField("codec_preference", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: "音频格式"
                    UiCombo { objectName: "profileAudioCodec"; Layout.fillWidth: true; accessibleName: "预设音频格式"; model: ["原始音频", "M4A", "MP3", "Opus", "FLAC"]; property var values: ["original", "m4a", "mp3", "opus", "flac"]; currentIndex: values.indexOf(settings.state.profileDraftAudioCodec); onActivated: settings.editProfileField("audio_codec", values[currentIndex]) }
                }
                SettingField { Layout.fillWidth: true; label: "转码音频质量"
                    UiCombo { objectName: "profileAudioQuality"; Layout.fillWidth: true; accessibleName: "预设音频质量"; model: ["原始", "320 kbps", "256 kbps", "192 kbps", "128 kbps"]; property var values: ["original", "320", "256", "192", "128"]; currentIndex: values.indexOf(settings.state.profileDraftAudioQuality); onActivated: settings.editProfileField("audio_quality", values[currentIndex]) }
                }
                UiSwitch { objectName: "profileSubtitleEnabled"; text: "下载字幕"; checked: settings.state.profileDraftSubtitleEnabled; onToggled: settings.editProfileField("subtitle_enabled", checked) }
                UiSwitch { objectName: "profileSubtitleAuto"; text: "包含自动生成字幕"; enabled: settings.state.profileDraftSubtitleEnabled; checked: settings.state.profileDraftSubtitleAuto; onToggled: settings.editProfileField("subtitle_auto", checked) }
                SettingField { Layout.fillWidth: true; label: "字幕格式"
                    UiCombo { objectName: "profileSubtitleFormat"; Layout.fillWidth: true; accessibleName: "预设字幕格式"; model: ["SRT", "VTT"]; property var values: ["srt", "vtt"]; currentIndex: values.indexOf(settings.state.profileDraftSubtitleFormat); enabled: settings.state.profileDraftSubtitleEnabled; onActivated: settings.editProfileField("subtitle_format", values[currentIndex]) }
                }
                UiSwitch { objectName: "profileSubtitleEmbed"; text: "嵌入视频"; enabled: settings.state.profileDraftSubtitleEnabled; checked: settings.state.profileDraftSubtitleEmbed; onToggled: settings.editProfileField("subtitle_embed", checked) }
                UiText { objectName: "profileEditorMessage"; Layout.fillWidth: true; visible: text.length > 0; text: settings.state.profileMessage; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
            }
        }
        footer: RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            UiButton { text: "取消"; onClicked: settings.closeProfileEditor() }
            UiButton { objectName: "saveProfile"; text: "保存"; appearance: "primary"; onClicked: settings.saveProfile() }
        }
    }
}

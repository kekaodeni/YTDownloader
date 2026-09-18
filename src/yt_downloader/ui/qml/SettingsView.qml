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
                SettingField {
                    Layout.fillWidth: true; label: "默认下载目录"
                    RowLayout { Layout.fillWidth: true
                        UiField { objectName: "defaultDirectory"; Layout.fillWidth: true; text: settings.state.download_directory; Accessible.name: "默认下载目录"; onTextChanged: settings.edit("download_directory", text) }
                        UiButton { text: "浏览"; onClicked: settings.browse_requested("download_directory") }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: root.width >= 720 ? 3 : 1; columnSpacing: 16; rowSpacing: 16
                    SettingField { Layout.fillWidth: true; label: "默认画质"
                        UiCombo { Layout.fillWidth: true; accessibleName: "默认画质"; model: ["自动推荐", "2160p", "1440p", "1080p", "720p"]; property var values: ["recommended", "2160p 4K", "1440p 2K", "1080p", "720p"]; currentIndex: Math.max(0, values.indexOf(settings.state.default_quality)); onActivated: settings.edit("default_quality", values[currentIndex]) }
                    }
                    SettingField { Layout.fillWidth: true; label: "分片并发"
                        UiCombo { Layout.fillWidth: true; accessibleName: "分片并发数"; model: ["自动", "1", "2", "4", "8"]; property var values: [0,1,2,4,8]; currentIndex: Math.max(0, values.indexOf(settings.state.concurrent_fragments)); onActivated: settings.edit("concurrent_fragments", values[currentIndex]) }
                    }
                    SettingField { Layout.fillWidth: true; label: "视频编码（高级）"
                        UiCombo { Layout.fillWidth: true; accessibleName: "视频编码偏好"; model: ["自动推荐", "AV1", "VP9", "H.264"]; property var values: ["auto", "av1", "vp9", "h264"]; currentIndex: Math.max(0, values.indexOf(settings.state.codec_preference)); onActivated: settings.edit("codec_preference", values[currentIndex]) }
                    }
                }
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
}

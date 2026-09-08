import QtQuick
import QtQuick.Layouts
Item {
    id: root; objectName: "aboutPage"
    UiScroll {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32
        contentHeight: content.implicitHeight
        ColumnLayout {
            id: content; width: parent.width - 12; spacing: 24
            UiText { text: "关于"; role: "PageTitle" }
            Item { Layout.preferredHeight: 20 }
            Image { source: assetsBase + "app-icon.png"; Layout.preferredWidth: 72; Layout.preferredHeight: 72; sourceSize.width: 144; sourceSize.height: 144 }
            ColumnLayout { Layout.fillWidth: true; spacing: 8
                UiText { text: "YT Downloader"; role: "PageTitle"; font.pointSize: 23 }
                UiText { text: "版本 " + shell.state.version; role: "Secondary"; color: theme.state.secondary }
            }
            UiText { Layout.fillWidth: true; text: "简洁的 Windows 11 YouTube 单视频下载器，由 yt-dlp、FFmpeg 与 PySide6 驱动。"; color: theme.state.secondary; wrapMode: Text.Wrap }
            Flow { Layout.fillWidth: true; spacing: 8
                UiButton { text: "在 GitHub 查看项目"; onClicked: shell.openProject() }
                UiButton { text: "复制项目地址"; visible: shell.state.projectError.length > 0; onClicked: shell.copyProject() }
            }
            UiText { Layout.fillWidth: true; text: shell.state.projectError; visible: text.length > 0; role: "Caption"; wrapMode: Text.WrapAnywhere }
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke }
            UiText { Layout.fillWidth: true; text: "本软件与 YouTube 无关联。请仅下载您有权保存的内容。第三方组件许可见发布目录。"; role: "Caption"; color: theme.state.muted; wrapMode: Text.Wrap }
        }
    }
}

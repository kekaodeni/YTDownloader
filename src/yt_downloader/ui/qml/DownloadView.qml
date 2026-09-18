import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "downloadPage"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32
        spacing: 18
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 6
                UiText { text: "下载"; role: "PageTitle" }
                UiText { text: "保存喜欢的视频，随时离线观看。"; role: "Secondary"; color: theme.state.secondary }
            }
            Item { Layout.fillWidth: true }
            UiText { text: download.tasks.count > 0 ? download.tasks.count + " 个任务" : ""; role: "Caption"; color: theme.state.muted }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            UiField {
                id: urlField; objectName: "urlInput"
                Layout.fillWidth: true; implicitHeight: 46
                placeholderText: "粘贴视频、播放列表或支持的网站链接…"
                text: download.state.url
                enabled: !download.state.busy
                Accessible.name: "视频、播放列表或网站链接"
                onTextChanged: download.setField("url", text)
                onAccepted: download.requestParse()
                rightPadding: clearUrl.visible ? 40 : 12
                UiButton { id: clearUrl; objectName: "clearUrl"; width: 32; height: 32; anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; visible: urlField.text.length > 0; text: "×"; hint: "清空链接"; appearance: "quiet"; onClicked: download.setField("url", "") }
            }
            UiButton {
                objectName: "parseButton"
                text: download.state.parseText; appearance: "primary"; implicitHeight: 46
                enabled: !download.state.cancelling
                onClicked: download.requestParse()
            }
        }
        UiText { Layout.fillWidth: true; visible: download.state.clipboardHint.length > 0 && !download.state.busy; text: download.state.clipboardHint; role: "Caption"; color: theme.state.muted; elide: Text.ElideRight }
        ColumnLayout {
            Layout.fillWidth: true; visible: download.state.busy; spacing: 8
            UiProgress { Layout.fillWidth: true; indeterminate: true }
            UiText { Layout.fillWidth: true; text: download.state.parseHint || (download.state.cancelling ? "正在停止解析…" : "正在获取视频信息…"); color: theme.state.secondary; role: "Caption"; wrapMode: Text.Wrap }
        }
        ListView {
            id: tasks
            objectName: "taskList"
            Layout.fillWidth: true; Layout.fillHeight: true
            model: download.tasks
            spacing: 12; clip: true; reuseItems: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { onPressedChanged: if (pressed) wheel.stop() }
            WheelSmoother { id: wheel; view: tasks }
            header: Column {
                width: tasks.width; spacing: 22
                Rectangle {
                    id: videoPanel
                    objectName: "videoPanel"
                    visible: download.state.ready
                    width: parent.width; height: visible ? info.implicitHeight + 40 : 0
                    color: theme.state.surface; radius: 14
                    border.color: theme.state.stroke
                    GridLayout {
                        id: info
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 20
                        columns: videoPanel.width >= 720 ? 2 : 1
                        rowSpacing: 18; columnSpacing: 24
                        Thumbnail {
                            Layout.preferredWidth: info.columns === 2 ? 260 : -1
                            Layout.fillWidth: info.columns === 1
                            Layout.preferredHeight: info.columns === 2 ? 146 : Math.min(width * 9 / 16, 260)
                            Layout.alignment: Qt.AlignTop
                            source: download.state.thumbnail
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 12
                            UiText { objectName: "videoTitle"; Layout.fillWidth: true; text: download.state.title; role: "CardTitle"; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
                            UiText { Layout.fillWidth: true; text: download.state.meta; color: theme.state.secondary; role: "Secondary"; elide: Text.ElideRight }
                            UiText { objectName: "compatibilityHint"; Layout.fillWidth: true; visible: text.length > 0; text: download.state.compatibilityHint; color: theme.state.muted; role: "Caption"; wrapMode: Text.Wrap }
                            UiText { Layout.fillWidth: true; visible: text.length > 0; text: download.state.mediaHint; color: theme.state.secondary; role: "Caption"; wrapMode: Text.Wrap }
                            UiText { text: "下载内容"; role: "Caption" }
                            UiCombo { objectName: "modeCombo"; Layout.fillWidth: true; accessibleName: "下载内容"; model: ["视频 + 音频", "仅视频", "仅音频"]; currentIndex: ["video_audio", "video_only", "audio_only"].indexOf(download.state.mediaMode); onActivated: download.selectMode(["video_audio", "video_only", "audio_only"][currentIndex]) }
                            UiText { Layout.fillWidth: true; visible: text.length > 0; text: download.state.modeHint; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                            UiCombo { objectName: "formatCombo"; visible: download.state.mediaMode !== "audio_only"; Layout.fillWidth: true; accessibleName: "下载清晰度"; model: download.state.formats; currentIndex: download.state.formatIndex; onActivated: download.selectFormat(currentIndex) }
                            UiCombo { objectName: "audioCodecCombo"; visible: download.state.mediaMode === "audio_only"; Layout.fillWidth: true; accessibleName: "音频格式"; model: ["原始音频（推荐）", "M4A", "MP3", "Opus", "FLAC"]; currentIndex: ["original", "m4a", "mp3", "opus", "flac"].indexOf(download.state.audioCodec); onActivated: download.selectAudio(["original", "m4a", "mp3", "opus", "flac"][currentIndex], download.state.audioQuality) }
                            UiCombo { visible: download.state.mediaMode === "audio_only"; enabled: download.state.audioCodec !== "original" && download.state.audioCodec !== "flac"; Layout.fillWidth: true; accessibleName: "音频质量"; model: ["原始", "320 kbps", "256 kbps", "192 kbps", "128 kbps"]; currentIndex: ["original", "320", "256", "192", "128"].indexOf(download.state.audioQuality); onActivated: download.selectAudio(download.state.audioCodec, ["original", "320", "256", "192", "128"][currentIndex]) }
                            UiField { objectName: "filenameInput"; Layout.fillWidth: true; Accessible.name: "输出文件名"; placeholderText: "文件名"; text: download.state.filename; onTextChanged: download.setField("filename", text) }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                UiField { objectName: "directoryInput"; Layout.fillWidth: true; Accessible.name: "下载目录"; text: download.state.directory; onTextChanged: download.setField("directory", text) }
                                UiButton { text: "浏览"; hint: "选择下载目录"; onClicked: download.browse_requested() }
                            }
                            UiText { Layout.fillWidth: true; text: download.state.technical; color: theme.state.muted; role: "Caption"; wrapMode: Text.Wrap }
                            RowLayout {
                                Layout.fillWidth: true
                                Item { Layout.fillWidth: true }
                                UiButton { objectName: "downloadButton"; text: "开始下载"; icon.source: assetsBase + "icons/arrow_download_regular.svg"; appearance: "primary"; enabled: download.state.ready && download.state.formats.length > 0 && !download.state.busy; onClicked: download.requestDownload() }
                            }
                        }
                    }
                    opacity: visible ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: shell.state.reduceMotion ? 0 : 240 } }
                }
                RowLayout {
                    visible: download.tasks.count > 0
                    width: parent.width
                    UiText { text: "下载任务"; role: "SectionTitle" }
                    Item { Layout.fillWidth: true }
                    UiText { text: "完成的任务会保存在历史记录"; role: "Caption"; color: theme.state.muted; visible: parent.width > 520 }
                }
                Item { width: 1; height: download.tasks.count > 0 ? 2 : 0 }
            }
            delegate: TaskCard { width: tasks.width - 10 }
            add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: shell.state.reduceMotion ? 0 : 240; easing.type: Easing.OutCubic } }
            remove: Transition { NumberAnimation { property: "opacity"; to: 0; duration: shell.state.reduceMotion ? 0 : 190 } }
            displaced: Transition { NumberAnimation { property: "y"; duration: shell.state.reduceMotion ? 0 : 240; easing.type: Easing.OutQuart } }
            Column {
                anchors.centerIn: parent; width: Math.min(340, parent.width - 32); spacing: 14
                visible: !download.state.ready && !download.state.busy && download.tasks.count === 0
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter; width: 64; height: 64; radius: 20; color: theme.state.selection
                    UiButton { anchors.centerIn: parent; icon.source: assetsBase + "icons/arrow_download_regular.svg"; icon.width: 28; icon.height: 28; appearance: "quiet"; selected: true; enabled: false; Accessible.ignored: true }
                }
                UiText { width: parent.width; text: "从一个链接开始"; role: "SectionTitle"; horizontalAlignment: Text.AlignHCenter }
                UiText { width: parent.width; text: "粘贴支持的网站链接，解析单个视频后选择清晰度、文件名和保存位置。"; role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }
    Connections { target: shell; function onScrollToTopRequested() { tasks.positionViewAtBeginning(); urlField.forceActiveFocus() } }
}

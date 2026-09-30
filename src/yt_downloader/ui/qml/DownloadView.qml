import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "downloadPage"
    readonly property int taskCount: download.tasks ? download.tasks.count : 0
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.width < 620 ? 20 : 32
        spacing: 18
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 6
                UiText { text: i18n.messages["nav.download"]; role: "PageTitle" }
                UiText { text: i18n.messages["download.subtitle"]; role: "Secondary"; color: theme.state.secondary }
            }
            Item { Layout.fillWidth: true }
            UiText { text: root.taskCount > 0 ? i18n.messages["download.task_count"].replace("{count}", root.taskCount) : ""; role: "Caption"; color: theme.state.muted }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            UiField {
                id: urlField; objectName: "urlInput"
                Layout.fillWidth: true; implicitHeight: 46
                placeholderText: i18n.messages["download.url_placeholder"]
                text: download.state.url
                enabled: !download.state.busy
                Accessible.name: i18n.messages["download.url_placeholder"]
                onTextChanged: download.setField("url", text)
                onAccepted: download.requestParse()
                rightPadding: clearUrl.visible ? 40 : 12
                UiButton { id: clearUrl; objectName: "clearUrl"; width: 32; height: 32; anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; visible: urlField.text.length > 0; text: "×"; hint: i18n.messages["download.link_clear"]; appearance: "quiet"; onClicked: download.setField("url", "") }
            }
            UiButton {
                objectName: "parseButton"
                text: download.state.parseText; appearance: "primary"; implicitHeight: 46
                enabled: !download.state.cancelling
                onClicked: download.requestParse()
            }
        }
        UiText { Layout.fillWidth: true; visible: download.state.clipboardHint.length > 0 && !download.state.busy; text: download.state.clipboardHint; role: "Caption"; color: theme.state.muted; elide: Text.ElideRight }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            UiText { text: i18n.messages["download.login_status"]; role: "Caption" }
            UiText {
                objectName: "cookieAuthStatus"
                visible: text.length > 0
                text: download.state.cookieAuthStatus
                role: "Caption"
                color: download.state.cookieAuthSeverity === "success" ? theme.state.success : download.state.cookieAuthSeverity === "error" ? theme.state.accent : theme.state.secondary
            }
            Item { Layout.fillWidth: true }
            UiSwitch { objectName: "useCookieSwitch"; text: i18n.messages["download.use_cookie"]; enabled: !download.state.busy; checked: download.state.cookieEnabled; onToggled: download.setCookieEnabled(checked) }
            UiButton { objectName: "cookieManagementButton"; text: i18n.messages["download.manage_cookie"]; appearance: "normal"; enabled: !download.state.busy; onClicked: shell.openCookieSettings() }
            UiButton { objectName: "cookieRetry"; text: i18n.messages["download.reparse"]; visible: download.state.cookieAuthInvalid; enabled: !download.state.busy; onClicked: download.requestParse() }
        }
        UiText {
            objectName: "cookieAuthWarning"
            Layout.fillWidth: true
            visible: download.state.cookieAuthWarning.length > 0 || download.state.cookieHint.length > 0
            text: download.state.cookieAuthWarning.length > 0 ? download.state.cookieAuthWarning : download.state.cookieHint
            role: "Caption"
            color: download.state.cookieAuthInvalid || download.state.cookieAuthWarning.length > 0 ? theme.state.accent : theme.state.secondary
            wrapMode: Text.Wrap
        }
        ColumnLayout {
            Layout.fillWidth: true; visible: download.state.busy; spacing: 8
            UiProgress { Layout.fillWidth: true; indeterminate: true }
            UiText { Layout.fillWidth: true; text: download.state.parseHint || (download.state.cancelling ? i18n.messages["download.stop_parsing"] : i18n.messages["download.fetching_info"]); color: theme.state.secondary; role: "Caption"; wrapMode: Text.Wrap }
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
            UiListViewport { id: viewport; objectName: "viewportAnchor"; view: tasks; header: tasks.headerItem }
            header: Column {
                width: tasks.width; spacing: 22
                property alias resultCard: videoPanel
                property alias disclosure: advancedToggle
                Rectangle {
                    id: videoPanel
                    objectName: "videoPanel"
                    // Keep the previous card's viewport while a replacement is
                    // loading; only accepted metadata requests a new position.
                    visible: download.state.ready || (download.state.busy && download.state.title.length > 0)
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
                            UiText { text: i18n.messages["download.content"]; role: "Caption" }
                            UiCombo { objectName: "modeCombo"; Layout.fillWidth: true; accessibleName: i18n.messages["download.content"]; model: [i18n.messages["download.mode.video_audio"], i18n.messages["download.mode.video_only"], i18n.messages["download.mode.audio_only"]]; currentIndex: ["video_audio", "video_only", "audio_only"].indexOf(download.state.mediaMode); onActivated: download.selectMode(["video_audio", "video_only", "audio_only"][currentIndex]) }
                            UiText { Layout.fillWidth: true; visible: text.length > 0; text: download.state.modeHint; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                            UiText { objectName: "collectionQualityLabel"; text: download.state.mediaMode === "audio_only" ? i18n.messages["download.audio_format"] : download.state.collection && download.state.collectionQualityMode === "DEFERRED_BATCH_TARGET" ? i18n.messages["download.batch_quality"] : i18n.messages["download.quality"]; role: "Caption" }
                            UiText { objectName: "formatSelectionHint"; Layout.fillWidth: true; visible: download.state.mediaMode !== "audio_only" && !download.state.collection; text: download.state.qualityAuto ? i18n.messages["download.quality_auto_hint"] : i18n.messages["download.quality_selected_hint"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                            UiCombo { objectName: download.state.collection ? "collectionQualityCombo" : "formatCombo"; visible: download.state.mediaMode !== "audio_only"; Layout.fillWidth: true; accessibleName: download.state.collection && download.state.collectionQualityMode === "DEFERRED_BATCH_TARGET" ? i18n.messages["download.batch_quality"] : i18n.messages["download.quality"]; model: download.state.collection ? download.state.collectionQualityLabels : download.state.formats; currentIndex: download.state.collection ? download.state.collectionQualityIndex : download.state.formatIndex; onActivated: download.state.collection ? download.selectCollectionQuality(currentIndex) : download.selectFormat(currentIndex) }
                            UiCombo { objectName: "audioCodecCombo"; visible: download.state.mediaMode === "audio_only"; Layout.fillWidth: true; accessibleName: i18n.messages["download.audio_format"]; model: [i18n.messages["download.audio_original_recommended"], "M4A", "MP3", "Opus", "FLAC"]; currentIndex: ["original", "m4a", "mp3", "opus", "flac"].indexOf(download.state.audioCodec); onActivated: download.selectAudio(["original", "m4a", "mp3", "opus", "flac"][currentIndex], download.state.audioQuality) }
                            UiText { text: i18n.messages["download.audio_quality"]; role: "Caption"; visible: download.state.mediaMode === "audio_only" }
                            UiCombo { visible: download.state.mediaMode === "audio_only"; enabled: download.state.audioCodec !== "original" && download.state.audioCodec !== "flac"; Layout.fillWidth: true; accessibleName: i18n.messages["download.audio_quality"]; model: [i18n.messages["download.audio_original"], "320 kbps", "256 kbps", "192 kbps", "128 kbps"]; currentIndex: ["original", "320", "256", "192", "128"].indexOf(download.state.audioQuality); onActivated: download.selectAudio(download.state.audioCodec, ["original", "320", "256", "192", "128"][currentIndex]) }
                            UiText { text: i18n.messages["download.subtitles"]; role: "Caption" }
                            RowLayout { Layout.fillWidth: true; spacing: 12; visible: download.state.subtitleEnabled
                                UiText { text: download.state.subtitleManualStatus; role: "Caption"; color: theme.state.secondary }
                                UiText { text: download.state.subtitleAutoStatus; role: "Caption"; color: theme.state.secondary }
                            }
                            UiSwitch { objectName: "subtitleEnabled"; text: i18n.messages["download.subtitles_action"]; enabled: download.state.subtitleCanDownload; checked: download.state.subtitleEnabled; onToggled: download.setSubtitleOption("enabled", checked) }
                            UiText { Layout.fillWidth: true; visible: download.state.subtitleCapability === "NONE"; text: i18n.messages["download.no_subtitles"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 8; visible: download.state.subtitleEnabled
                                UiSwitch { objectName: "subtitleAuto"; visible: download.state.subtitleCapability === "MANUAL_AND_AUTO"; text: i18n.messages["download.auto_subtitles"]; enabled: download.state.subtitleCanAuto; checked: download.state.subtitleAuto; onToggled: download.setSubtitleOption("auto", checked) }
                                UiText { visible: download.state.subtitleCapability === "AUTO_ONLY"; text: i18n.messages["download.auto_subtitles_only"]; role: "Caption"; color: theme.state.secondary }
                                ListView {
                                    Layout.fillWidth: true; Layout.preferredHeight: Math.min(count * 38, 190)
                                    clip: true; reuseItems: true; boundsBehavior: Flickable.StopAtBounds
                                    model: download.state.subtitleChoices
                                    delegate: UiSwitch { required property var modelData; width: ListView.view.width; text: modelData.name; checked: modelData.selected; onToggled: download.selectSubtitle(modelData.code, checked) }
                                    ScrollBar.vertical: ScrollBar {}
                                }
                                UiText { text: i18n.messages["download.subtitle_format"]; role: "Caption" }
                                UiCombo { objectName: "subtitleFormat"; enabled: download.state.subtitleCanFormat; Layout.preferredWidth: 280; accessibleName: i18n.messages["download.subtitle_format"]; model: ["SRT", "VTT"]; currentIndex: download.state.subtitleFormat === "srt" ? 0 : 1; onActivated: download.selectSubtitleFormat(currentIndex === 0 ? "srt" : "vtt") }
                                UiSwitch { objectName: "subtitleEmbed"; visible: download.state.subtitleCanEmbed; text: i18n.messages["download.embed_subtitle"]; checked: download.state.subtitleEmbed; enabled: download.state.subtitleCanEmbed; onToggled: download.setSubtitleOption("embed", checked) }
                                UiText { Layout.fillWidth: true; visible: download.state.subtitleEnabled; text: download.state.subtitleEmbed ? i18n.messages["download.embed_subtitle_hint"] : i18n.messages["download.subtitle_separate_hint"]; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                                UiText { Layout.fillWidth: true; text: download.state.subtitleEmbedHint; visible: text.length > 0 && download.state.subtitleCapability !== "NONE"; role: "Caption"; color: theme.state.secondary; wrapMode: Text.Wrap }
                            }
                            SettingField {
                                objectName: "filenameField"
                                Layout.fillWidth: true; visible: !download.state.collection; label: i18n.messages["download.filename"]
                                UiField { objectName: "filenameInput"; Layout.fillWidth: true; implicitHeight: 40; Accessible.name: i18n.messages["download.filename"]; placeholderText: i18n.messages["download.filename"]; text: download.state.filename; onTextEdited: download.setField("filename", text) }
                            }
                            SettingField {
                                objectName: "directoryField"
                                Layout.fillWidth: true; visible: true; label: i18n.messages["download.save_location"]
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 8
                                    UiField { objectName: "directoryInput"; Layout.fillWidth: true; implicitHeight: 40; Accessible.name: i18n.messages["download.directory"]; text: download.state.directory; onTextChanged: if (text !== download.state.directory) download.setField("directory", text) }
                                    UiButton { text: i18n.messages["common.browse"]; hint: i18n.messages["download.save_location"]; onClicked: download.browse_requested() }
                                }
                            }
                            UiText { Layout.fillWidth: true; visible: download.state.collection; text: i18n.messages["collection.filename_hint"]; role: "Caption"; color: theme.state.secondary }
                            ColumnLayout {
                                Layout.fillWidth: true; visible: download.state.collection; spacing: 8
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 14
                                    CheckBox {
                                        id: collectionSelectAll
                                        objectName: "collectionSelectAll"
                                        text: i18n.messages["history.select_all"]
                                        tristate: true
                                        checkState: download.state.collectionSelectState
                                        nextCheckState: function() { return download.state.collectionSelectState }
                                        enabled: download.state.collectionSelectableCount > 0
                                        Accessible.name: i18n.messages["history.select_all"]
                                        Accessible.description: checkState === Qt.Checked ? i18n.messages["history.selection.all"] : checkState === Qt.PartiallyChecked ? i18n.messages["history.selection.partial"] : i18n.messages["history.selection.unselected"]
                                        onClicked: download.selectAllEntries(checkState !== Qt.Checked)
                                    }
                                    UiText { text: i18n.messages["collection.selected_count"].replace("{selected}", download.state.selectedCount).replace("{total}", download.state.collectionSelectableCount); role: "Caption"; color: theme.state.secondary }
                                }
                                ListView {
                                    objectName: "collectionItems"
                                    Layout.fillWidth: true; Layout.preferredHeight: Math.min(count * 76, 380)
                                    model: download.entries; clip: true; reuseItems: true
                                    boundsBehavior: Flickable.StopAtBounds; spacing: 3
                                    ScrollBar.vertical: ScrollBar {}
                                    delegate: Rectangle {
                                        required property var item
                                        width: ListView.view.width; height: 72; radius: 8
                                        color: item.selected ? theme.state.selection : rowHover.hovered ? theme.state.subtle : "transparent"
                                        border.color: item.selected ? theme.state.accent : "transparent"
                                        RowLayout {
                                            z: 1
                                            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 10
                                            CheckBox {
                                                id: entryCheck
                                                objectName: "collectionEntryCheck-" + item.index
                                                enabled: !item.unavailable
                                                checked: item.selected
                                                Accessible.name: item.title
                                                onClicked: download.selectEntry(item.index, !item.selected)
                                            }
                                            Thumbnail { Layout.preferredWidth: 64; Layout.preferredHeight: 40; source: item.thumbnail; visible: parent.width > 380 }
                                            ColumnLayout {
                                                Layout.fillWidth: true; spacing: 3
                                                UiText { objectName: "collectionEntryTitle-" + item.index; Layout.fillWidth: true; text: item.title; elide: Text.ElideRight; maximumLineCount: 1 }
                                                UiText { Layout.fillWidth: true; text: item.unavailable ? i18n.messages["collection.unavailable"] : item.detail; role: "Caption"; color: theme.state.secondary; elide: Text.ElideRight }
                                            }
                                        }
                                        HoverHandler { id: rowHover }
                                        TapHandler {
                                            id: entryTap
                                            acceptedButtons: Qt.LeftButton
                                            onTapped: function(point) {
                                                if (!item.unavailable && point.position.x > entryCheck.width + 24)
                                                    download.selectEntry(item.index, !item.selected)
                                            }
                                        }
                                    }
                                }
                                UiText { Layout.fillWidth: true; text: i18n.messages["collection.guidance"]; wrapMode: Text.Wrap; role: "Caption"; color: theme.state.secondary }
                            }
                            UiDisclosure {
                                id: advancedToggle
                                label: i18n.messages["download.advanced"]
                                expanded: download.state.advancedExpanded
                                onClicked: { viewport.prepare(advancedToggle, download.state.advancedExpanded ? advancedPanel.height + 16 : 0); download.setAdvancedToggle("advancedExpanded", !download.state.advancedExpanded) }
                            }
                            Rectangle {
                                id: advancedPanel
                                objectName: "advancedOptionsPanel"
                                Layout.fillWidth: true
                                visible: download.state.advancedExpanded
                                implicitHeight: visible ? panelContent.implicitHeight + 28 : 0
                                color: theme.state.elevated
                                radius: 12
                                border.width: 1
                                border.color: theme.state.stroke
                                ColumnLayout {
                                    id: panelContent
                                    anchors.fill: parent
                                    anchors.margins: 14
                                    spacing: 16
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        visible: !download.state.collection
                                        spacing: 8
                                        UiText { text: i18n.messages["clip.title"]; role: "SectionTitle" }
                                        UiSettingToggle {
                                            id: clipToggle
                                            objectName: "clipEnabled"
                                            label: i18n.messages["clip.range_toggle"]
                                            checked: download.state.clipEnabled
                                            onChanged: function(value) { viewport.prepare(clipToggle, value ? 0 : clipFields.implicitHeight); download.setAdvancedToggle("clipEnabled", value) }
                                        }
                                        Item {
                                            objectName: "clipFieldsContainer"
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: download.state.clipEnabled ? clipFields.implicitHeight : 0
                                            clip: true
                                            ColumnLayout {
                                                id: clipFields
                                                width: parent.width
                                                spacing: 8
                                                opacity: download.state.clipEnabled ? 1 : 0
                                                enabled: download.state.clipEnabled
                                                Behavior on opacity { NumberAnimation { duration: motion.standard } }
                                                GridLayout {
                                                    Layout.fillWidth: true
                                                    columns: width >= 560 ? 2 : 1
                                                    columnSpacing: 14
                                                    rowSpacing: 10
                                                    ColumnLayout {
                                                        Layout.fillWidth: true
                                                        UiText { text: i18n.messages["clip.start"]; role: "Caption" }
                                                        UiTimeField {
                                                            objectName: "clipStart"
                                                            Layout.fillWidth: true
                                                            Accessible.name: i18n.messages["clip.start"]
                                                            timecode: ({longFormat: download.state.clipLongFormat, value: download.state.clipStart})
                                                            onValueEdited: function(value) { download.setAdvancedField("clipStart", value) }
                                                        }
                                                    }
                                                    ColumnLayout {
                                                        Layout.fillWidth: true
                                                        UiText { text: i18n.messages["clip.end"]; role: "Caption" }
                                                        UiTimeField {
                                                            objectName: "clipEnd"
                                                            Layout.fillWidth: true
                                                            Accessible.name: i18n.messages["clip.end"]
                                                            timecode: ({longFormat: download.state.clipLongFormat, value: download.state.clipEnd})
                                                            onValueEdited: function(value) { download.setAdvancedField("clipEnd", value) }
                                                        }
                                                    }
                                                    UiText {
                                                        objectName: "clipError"
                                                        Layout.fillWidth: true
                                                        Layout.columnSpan: 2
                                                        visible: download.state.clipError.length > 0
                                                        text: download.state.clipError
                                                        role: "Caption"
                                                        color: theme.state.accent
                                                        wrapMode: Text.Wrap
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    Rectangle { Layout.fillWidth: true; height: 1; color: theme.state.stroke; opacity: 0.65 }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        UiText { text: i18n.messages["postprocess.title"]; role: "SectionTitle" }
                                        UiSettingToggle {
                                            objectName: "embedThumbnail"
                                            label: i18n.messages["postprocess.embed_thumbnail"]
                                            checked: download.state.embedThumbnail
                                            onChanged: function(value) { download.setAdvancedToggle("embedThumbnail", value) }
                                        }
                                        UiSettingToggle {
                                            objectName: "embedMetadata"
                                            label: i18n.messages["postprocess.embed_metadata"]
                                            checked: download.state.embedMetadata
                                            onChanged: function(value) { download.setAdvancedToggle("embedMetadata", value) }
                                        }
                                        UiSettingToggle {
                                            objectName: "embedChapters"
                                            label: i18n.messages["postprocess.embed_chapters"]
                                            checked: download.state.embedChapters
                                            onChanged: function(value) { download.setAdvancedToggle("embedChapters", value) }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            visible: download.state.mediaMode !== "audio_only"
                                            spacing: 14
                                            UiText { Layout.fillWidth: true; text: i18n.messages["postprocess.remux"]; role: "Body"; elide: Text.ElideRight }
                                            UiCombo {
                                                objectName: "remuxContainer"
                                                Layout.preferredWidth: 220
                                                Layout.minimumWidth: 160
                                                Layout.maximumWidth: 240
                                                accessibleName: i18n.messages["postprocess.remux"]
                                                property var values: ["", "mp4", "mkv", "webm"]
                                                model: [i18n.messages["postprocess.original"], "MP4", "MKV", "WebM"]
                                                currentIndex: Math.max(0, values.indexOf(download.state.remuxContainer))
                                                onActivated: download.setAdvancedField("remuxContainer", values[currentIndex])
                                            }
                                        }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        visible: download.state.mediaSite === "youtube" && !download.state.collection
                                        spacing: 8
                                        UiText { text: i18n.messages["postprocess.sponsorblock_title"]; role: "SectionTitle" }
                                        UiSettingToggle {
                                            objectName: "sponsorblockMark"
                                            label: i18n.messages["postprocess.sponsorblock_mark"]
                                            checked: download.state.sponsorblockMark
                                            onChanged: function(value) { download.setAdvancedToggle("sponsorblockMark", value) }
                                        }
                                    }
                                }
                            }
                            UiText { objectName: "technicalSummary"; Layout.fillWidth: true; text: download.state.technical; color: theme.state.muted; role: "Caption"; wrapMode: Text.Wrap }
                            RowLayout {
                                Layout.fillWidth: true
                                Item { Layout.fillWidth: true }
                                UiButton { objectName: "downloadButton"; text: download.state.collection ? i18n.messages["collection.start_download"].replace("{count}", download.state.selectedCount) : i18n.messages["download.start"]; icon.source: assetsBase + "icons/arrow_download_regular.svg"; appearance: "primary"; enabled: download.state.ready && (download.state.collection ? download.state.selectedCount > 0 : download.state.formats.length > 0 && download.state.clipValid) && !download.state.busy; onClicked: download.requestDownload() }
                            }
                        }
                    }
                    opacity: visible ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: motion.standard } }
                }
                RowLayout {
                    visible: root.taskCount > 0 || videoPanel.visible
                    width: parent.width
                    UiText { text: i18n.messages["download.tasks"]; role: "SectionTitle" }
                    Item { Layout.fillWidth: true }
                    UiText { text: i18n.messages["download.task_history_hint"]; role: "Caption"; color: theme.state.muted; visible: parent.width > 520 }
                }
                Item { width: 1; height: root.taskCount > 0 || videoPanel.visible ? 2 : 0 }
            }
            delegate: TaskCard { width: tasks.width - 10 }
            footer: Item { width: tasks.width; height: viewport.boundaryReserve }
            add: Transition { ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.standard; easing.type: motion.easing }
                NumberAnimation { property: "entranceOffset"; from: motion.reduced ? 0 : 6; to: 0; duration: motion.movement; easing.type: motion.easing }
            } }
            remove: Transition { NumberAnimation { property: "opacity"; to: 0; duration: motion.fast } }
            displaced: Transition { NumberAnimation { property: "y"; duration: motion.movement; easing.type: motion.easing } }
            Connections {
                target: download
                function onTaskRemoving(taskId) {
                    if (tasks.count === 1 && download.state.ready)
                        viewport.prepare(tasks.headerItem.disclosure, Math.max(0, tasks.contentHeight - tasks.headerItem.height), true)
                }
            }
            Column {
                anchors.centerIn: parent; width: Math.min(340, parent.width - 32); spacing: 14
                visible: !download.state.ready && !download.state.busy && root.taskCount === 0
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter; width: 64; height: 64; radius: 20; color: theme.state.selection
                    UiButton { anchors.centerIn: parent; icon.source: assetsBase + "icons/arrow_download_regular.svg"; icon.width: 28; icon.height: 28; appearance: "quiet"; selected: true; enabled: false; Accessible.ignored: true }
                }
                UiText { width: parent.width; text: i18n.messages["download.empty.title"]; role: "SectionTitle"; horizontalAlignment: Text.AlignHCenter }
                UiText { width: parent.width; text: i18n.messages["download.empty.body"]; role: "Secondary"; color: theme.state.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }
    Connections {
        target: shell
        // Emitted only after the controller's generation gate accepts metadata.
        function onScrollToTopRequested() {
            wheel.stop()
            tasks.cancelFlick()
            viewport.positionAt(tasks.headerItem.resultCard)
        }
    }
}

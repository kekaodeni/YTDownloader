import QtQuick

Rectangle {
    id: root
    property string source: ""
    property string placeholder: i18n.messages["thumbnail.none"]
    property string current: ""
    property int imageFillMode: Image.PreserveAspectCrop
    readonly property real sourceAspectRatio: incoming.status === Image.Ready && incoming.implicitHeight > 0
        ? incoming.implicitWidth / incoming.implicitHeight
        : outgoing.status === Image.Ready && outgoing.implicitHeight > 0 ? outgoing.implicitWidth / outgoing.implicitHeight : 16 / 9
    color: theme.state.subtle
    radius: 10
    clip: true
    onSourceChanged: {
        if (incoming.status === Image.Ready && incoming.opacity > 0.5) current = incoming.source
        incoming.opacity = 0
        incoming.source = source
        if (!source) current = ""
    }
    UiText { anchors.centerIn: parent; text: root.placeholder; role: "Caption"; color: theme.state.muted; visible: !root.current && incoming.status !== Image.Ready }
    Image { id: outgoing; anchors.fill: parent; source: root.current; fillMode: root.imageFillMode; asynchronous: true; cache: true; sourceSize.width: 720; sourceSize.height: 720 }
    Image {
        id: incoming
        anchors.fill: parent
        opacity: 0
        fillMode: root.imageFillMode
        asynchronous: true
        cache: true
        sourceSize.width: 720; sourceSize.height: 720
        onStatusChanged: if (status === Image.Ready) { opacity = 1; root.current = source }
    }
}

import QtQuick

Rectangle {
    id: root
    property string source: ""
    property string placeholder: "暂无封面"
    property string current: ""
    property int imageFillMode: Image.PreserveAspectCrop
    readonly property real sourceAspectRatio: incoming.status === Image.Ready && incoming.implicitHeight > 0
        ? incoming.implicitWidth / incoming.implicitHeight
        : outgoing.status === Image.Ready && outgoing.implicitHeight > 0 ? outgoing.implicitWidth / outgoing.implicitHeight : 16 / 9
    color: theme.state.subtle
    radius: 10
    clip: true
    onSourceChanged: {
        blend.stop()
        if (incoming.status === Image.Ready && incoming.opacity > 0.5) current = incoming.source
        incoming.opacity = 0
        incoming.source = source
        if (!source) current = ""
    }
    UiText { anchors.centerIn: parent; text: root.placeholder; role: "Caption"; color: theme.state.muted; visible: !root.current && incoming.status !== Image.Ready }
    Image { id: outgoing; anchors.fill: parent; source: root.current; fillMode: root.imageFillMode; asynchronous: true; sourceSize.width: 720; sourceSize.height: 720 }
    Image {
        id: incoming
        anchors.fill: parent
        opacity: 0
        fillMode: root.imageFillMode
        asynchronous: true
        sourceSize.width: 720; sourceSize.height: 720
        onStatusChanged: if (status === Image.Ready) blend.restart()
    }
    NumberAnimation {
        id: blend; target: incoming; property: "opacity"; to: 1
        duration: shell.state.reduceMotion ? 0 : 180
        easing.type: Easing.OutCubic
        onFinished: root.current = incoming.source
    }
}

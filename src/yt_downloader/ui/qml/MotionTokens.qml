import QtQuick

// One policy for application motion. Page values preserve the existing shell.
QtObject {
    objectName: "motionTokens"
    readonly property bool reduced: shell.state.reduceMotion
    readonly property int micro: reduced ? 70 : 120
    readonly property int fast: reduced ? 80 : 140
    readonly property int standard: reduced ? 80 : 180
    readonly property int page: reduced ? 80 : 220
    readonly property int geometry: reduced ? 0 : 170
    readonly property int movement: reduced ? 0 : standard
    readonly property int easing: Easing.OutCubic
    readonly property real pageOffset: reduced ? 0 : 8
    readonly property real categoryOffset: reduced ? 0 : 6
    readonly property real popupScale: reduced ? 1 : 0.985
}

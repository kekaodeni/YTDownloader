import QtQuick

UiField {
    id: control
    property var timecode: ({longFormat: true, value: ""})
    property bool applying: false
    property int previousPosition: 0
    signal valueEdited(string value)
    function synchronize() {
        applying = true
        const mask = timecode.longFormat ? "99:99:99;_" : "99:99;_"
        if (inputMask !== mask) inputMask = mask
        if (text !== timecode.value && getText(0, length) !== timecode.value)
            text = timecode.value
        applying = false
    }
    onTimecodeChanged: synchronize()
    Component.onCompleted: synchronize()
    onTextEdited: {
        if (applying) return
        const value = getText(0, length)
        if (/^[0-9:_]*$/.test(value)) valueEdited(value)
        else synchronize()
    }
    onCursorPositionChanged: {
        if (displayText.charAt(cursorPosition) === ":")
            cursorPosition += cursorPosition < previousPosition ? -1 : 1
        previousPosition = cursorPosition
    }
    placeholderText: timecode.longFormat ? "HH:MM:SS" : "MM:SS"
    inputMethodHints: Qt.ImhDigitsOnly | Qt.ImhNoPredictiveText
    // The mask supplies separators and native selection, deletion and paste.
    // Reject non-ASCII digits before publishing; incomplete and out-of-range
    // edits use the existing presenter validation and cannot start a download.
}

import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: control
    implicitHeight: 40
    implicitWidth: 200
    leftPadding: 12
    rightPadding: 12
    color: enabled ? theme.state.text : theme.state.disabled
    placeholderTextColor: theme.state.muted
    selectionColor: theme.state.selection
    selectedTextColor: theme.state.text
    // The Python-side font assignment preserves the complete fallback stack;
    // a declarative family binding would collapse it back to the host default.
    onTextChanged: theme.applyFont(control, "Body", text || placeholderText)
    onPlaceholderTextChanged: if (!text) theme.applyFont(control, "Body", placeholderText)
    selectByMouse: true
    background: Rectangle {
        radius: 8
        color: control.enabled ? theme.state.surface : theme.state.subtle
        border.color: control.activeFocus ? theme.state.accent : control.hovered ? theme.state.muted : theme.state.stroke
        border.width: control.activeFocus ? 2 : 1
        Behavior on border.color { ColorAnimation { duration: shell.state.reduceMotion ? 0 : 100 } }
    }
}

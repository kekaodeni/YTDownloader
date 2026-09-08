import QtQuick
import QtQuick.Controls.Basic

ComboBox {
    id: control
    implicitHeight: 40
    implicitWidth: 200
    leftPadding: 12
    rightPadding: 34
    font.family: theme.fontFamily("Body", displayText)
    font.pointSize: theme.fontSize("Body")
    font.weight: theme.fontWeight("Body")
    Accessible.name: control.accessibleName
    property string accessibleName: "选择选项"
    contentItem: UiText {
        text: control.displayText
        color: control.enabled ? theme.state.text : theme.state.disabled
        elide: Text.ElideRight
    }
    indicator: Image {
        width: 16; height: 16
        x: control.width - 27; y: (control.height - height) / 2
        source: assetsBase + "icons/chevron_down_" + (theme.state.dark ? "dark" : "light") + ".svg"
    }
    background: Rectangle {
        radius: 8; color: control.enabled ? theme.state.surface : theme.state.subtle
        border.color: control.visualFocus ? theme.state.accent : theme.state.stroke
        border.width: control.visualFocus ? 2 : 1
    }
    delegate: ItemDelegate {
        width: control.width - 12; height: 38
        highlighted: control.highlightedIndex === index
        contentItem: UiText { text: modelData; elide: Text.ElideRight }
        background: Rectangle { radius: 6; color: parent.highlighted ? theme.state.selection : parent.hovered ? theme.state.subtle : "transparent" }
    }
    popup: Popup {
        y: control.height + 5
        width: control.width
        padding: 6
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 280)
        background: Rectangle { color: theme.state.elevated; radius: 10; border.color: theme.state.stroke }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: shell.state.reduceMotion ? 0 : 180; easing.type: Easing.OutCubic } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: shell.state.reduceMotion ? 0 : 140 } }
    }
}

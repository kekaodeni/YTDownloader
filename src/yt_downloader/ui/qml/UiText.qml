import QtQuick

Text {
    property string role: "Body"
    color: theme.state.text
    font.family: theme.fontFamily(role, text)
    font.pointSize: theme.fontSize(role)
    font.weight: theme.fontWeight(role)
    textFormat: Text.PlainText
    renderType: Text.QtRendering
    verticalAlignment: Text.AlignVCenter
}

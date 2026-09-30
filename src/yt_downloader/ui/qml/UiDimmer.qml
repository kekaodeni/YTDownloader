import QtQuick

Rectangle {
    color: "#550C1524"
    Behavior on opacity { NumberAnimation { duration: motion.standard; easing.type: motion.easing } }
}

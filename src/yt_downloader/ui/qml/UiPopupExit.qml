import QtQuick

Transition {
    id: transition
    property int duration: motion.fast
    ParallelAnimation {
        NumberAnimation { property: "opacity"; to: 0; duration: transition.duration; easing.type: motion.easing }
        NumberAnimation { property: "scale"; to: motion.popupScale; duration: motion.reduced ? 0 : transition.duration; easing.type: motion.easing }
    }
}

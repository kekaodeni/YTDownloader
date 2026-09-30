import QtQuick

Transition {
    id: transition
    property int duration: motion.fast
    ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: transition.duration; easing.type: motion.easing }
        NumberAnimation { property: "scale"; from: motion.popupScale; to: 1; duration: motion.reduced ? 0 : transition.duration; easing.type: motion.easing }
    }
}

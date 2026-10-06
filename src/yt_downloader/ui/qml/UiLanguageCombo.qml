import QtQuick

UiCombo {
    id: languageSelector
    readonly property var languages: i18n.languages
    property string pendingLocale: ""
    model: languages.map(function(language) { return language.name })
    currentIndex: Math.max(0, languages.findIndex(function(language) { return language.locale === settings.state.language }))
    function applyPendingLocale() {
        const locale = pendingLocale
        pendingLocale = ""
        if (locale.length) settings.setSetting("language", locale)
    }
    onActivated: function(index) {
        pendingLocale = languages[index].locale
        if (popup.visible) popup.close()
        else applyPendingLocale() // Closed-popup keyboard activation is already safe.
    }
    Connections {
        target: languageSelector.popup
        function onClosed() {
            languageSelector.applyPendingLocale()
        }
    }
}

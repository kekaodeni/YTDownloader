"""Map UI locales to native YouTube translated textual metadata preferences."""

_YOUTUBE_LANGUAGES = {
    'zh-CN': 'zh-CN', 'zh-TW': 'zh-TW', 'en-US': 'en', 'ja-JP': 'ja',
    'ko-KR': 'ko', 'ru-RU': 'ru', 'es-ES': 'es', 'pt-BR': 'pt',
    'vi-VN': 'vi', 'th-TH': 'th',
}


def youtube_metadata_options(ui_language: str) -> dict:
    language = _YOUTUBE_LANGUAGES.get(ui_language)
    if language is None and ui_language in _YOUTUBE_LANGUAGES.values():
        language = ui_language
    # Legacy/service callers with no UI locale retain native extraction defaults.
    return {'extractor_args': {'youtube': {'lang': [language]}}} if language else {}

package com.witchercookbook.util

/**
 * Answer language detected from a user query (spec FR-4).
 *
 * @property instructionName how the language is named in the prompt instruction
 *   ("answer in $instructionName") built by `PromptBuilder`.
 */
enum class Language(val tag: String, val instructionName: String) {
    ENGLISH("en", "English"),
    RUSSIAN("ru", "Russian"),
    POLISH("pl", "Polish"),
}

/**
 * Lightweight query-language heuristic: no ML model, no dependency, unit-testable
 * without Ollama (NFR-6). Distinguishes Russian (Cyrillic script), Polish (Latin
 * script with Polish-specific diacritics or common words), and defaults to English
 * otherwise — the knowledge base and embeddings are English regardless (FR-4).
 */
object LanguageDetector {

    private val CYRILLIC_RANGE = 'Ѐ'..'ӿ'

    private val POLISH_DIACRITICS = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ".toSet()

    /** Common Polish function words, unaccented, so ASCII-only Polish still detects. */
    private val POLISH_WORDS = setOf(
        "w", "na", "z", "nie", "jest", "co", "jak", "czy",
        "proszę", "prosze", "przepis", "danie", "dla", "mnie", "chciałbym", "chcialbym",
    )

    fun detect(text: String): Language {
        if (text.any { it in CYRILLIC_RANGE }) return Language.RUSSIAN
        if (text.any { it in POLISH_DIACRITICS }) return Language.POLISH
        if (containsPolishWord(text)) return Language.POLISH
        return Language.ENGLISH
    }

    private fun containsPolishWord(text: String): Boolean {
        val words = text.lowercase().split(Regex("[^\\p{L}]+")).filter { it.isNotBlank() }
        return words.any { it in POLISH_WORDS }
    }
}

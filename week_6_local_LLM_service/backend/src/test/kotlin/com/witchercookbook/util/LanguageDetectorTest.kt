package com.witchercookbook.util

import kotlin.test.Test
import kotlin.test.assertEquals

class LanguageDetectorTest {

    @Test
    fun `detects English by default`() {
        assertEquals(Language.ENGLISH, LanguageDetector.detect("Give me a recipe for a hearty soup"))
    }

    @Test
    fun `detects Russian from Cyrillic script`() {
        assertEquals(Language.RUSSIAN, LanguageDetector.detect("Дай мне рецепт сытного супа"))
    }

    @Test
    fun `detects Polish from diacritics`() {
        assertEquals(Language.POLISH, LanguageDetector.detect("Chciałbym przepis na pyszną zupę"))
    }

    @Test
    fun `detects Polish from common words without diacritics`() {
        assertEquals(Language.POLISH, LanguageDetector.detect("Prosze o przepis na zupe dla mnie"))
    }

    @Test
    fun `mixed script prefers Russian since KB is English-only fallback is unaffected`() {
        assertEquals(Language.RUSSIAN, LanguageDetector.detect("hearty stew рецепт"))
    }

    @Test
    fun `blank text defaults to English`() {
        assertEquals(Language.ENGLISH, LanguageDetector.detect(""))
    }
}

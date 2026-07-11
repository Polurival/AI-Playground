package com.witchercookbook.rag

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ChunkerTest {

    /** Word-count estimator makes chunk boundaries crisp and independent of prose length. */
    private val byWords: (String) -> Int =
        { it.split(Regex("\\s+")).count { w -> w.isNotBlank() } }

    @Test
    fun `short doc yields a single chunk carrying metadata`() {
        val doc = ParsedDoc("Novigrad", "locations", "A short body about the free city.")
        val chunks = Chunker().chunk(doc, "locations/novigrad")

        assertEquals(1, chunks.size)
        val c = chunks.single()
        assertEquals("locations/novigrad#0", c.id)
        assertEquals("Novigrad", c.title)
        assertEquals("locations", c.category)
        assertEquals("A short body about the free city.", c.text)
    }

    @Test
    fun `blank body yields no chunks`() {
        val doc = ParsedDoc("Empty", "meals", "   \n\n  ")
        assertTrue(Chunker().chunk(doc, "meals/empty").isEmpty())
    }

    @Test
    fun `long body splits into sequential, overlapping chunks`() {
        // Four distinct 5-word sentences in one paragraph; small caps force a sentence split.
        val body = "Alpha alpha alpha alpha alpha. " +
            "Bravo bravo bravo bravo bravo. " +
            "Charlie charlie charlie charlie charlie. " +
            "Delta delta delta delta delta."
        val chunker = Chunker(targetTokens = 6, maxTokens = 8, overlapTokens = 2, estimateTokens = byWords)

        val chunks = chunker.chunk(ParsedDoc("Doc", "meals", body), "meals/doc")

        assertTrue(chunks.size > 1, "expected multiple chunks, got ${chunks.size}")
        // Ids are sequential and 0-based.
        chunks.forEachIndexed { i, c -> assertEquals("meals/doc#$i", c.id) }
        // Consecutive chunks overlap: each chunk's tail sentence reappears at the next chunk's head.
        for (i in 0 until chunks.size - 1) {
            val prevTail = chunks[i].text.split(Regex("(?<=[.!?])\\s+")).last().trim()
            assertTrue(
                chunks[i + 1].text.startsWith(prevTail),
                "chunk ${i + 1} '${chunks[i + 1].text}' should start with prev tail '$prevTail'",
            )
        }
    }

    @Test
    fun `chunks never span a heading`() {
        val body = """
            ## Ingredients

            Venison, juniper, root vegetables, dark bread.

            ## Method

            Brown the meat, then braise it slowly with the vegetables.
        """.trimIndent()
        // Large caps so each section collapses to exactly one chunk.
        val chunker = Chunker(targetTokens = 200, maxTokens = 400, overlapTokens = 10, estimateTokens = byWords)

        val chunks = chunker.chunk(ParsedDoc("Stew", "meals", body), "meals/stew")

        assertEquals(2, chunks.size)
        assertTrue(chunks[0].text.contains("Ingredients") && chunks[0].text.contains("Venison"))
        assertTrue(chunks[1].text.contains("Method") && chunks[1].text.contains("braise"))
        // No cross-heading bleed.
        assertTrue(!chunks[0].text.contains("Method"))
        assertTrue(!chunks[1].text.contains("Ingredients"))
    }

    @Test
    fun `default char estimator keeps normal chunks within the max`() {
        // A realistic ~2500-char body should split, with each non-overlap-seeded chunk under max.
        val paragraph = "The tavern keeps a large pot of stew simmering at all hours, " +
            "replenished with whatever meat and vegetables arrive that morning. "
        val body = (1..12).joinToString("\n\n") { paragraph.trim() }

        val chunks = Chunker(targetTokens = 120, maxTokens = 160).chunk(
            ParsedDoc("Tavern", "taverns", body), "taverns/x",
        )

        assertTrue(chunks.size > 1)
        chunks.forEach { c ->
            assertTrue(
                estimateTokensByChars(c.text) <= 200,
                "chunk exceeded a sane bound: ${estimateTokensByChars(c.text)} tokens",
            )
        }
    }
}

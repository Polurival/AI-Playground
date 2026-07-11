package com.witchercookbook.rag

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class MarkdownParserTest {

    @Test
    fun `parses title, category and trimmed body`() {
        val raw = """
            ---
            title: Redanian Goulash
            category: meals
            ---

            Redanian goulash reflects southern trade influence.

            Serve with buckwheat groats.
        """.trimIndent()

        val doc = MarkdownParser.parse(raw)

        assertEquals("Redanian Goulash", doc.title)
        assertEquals("meals", doc.category)
        assertTrue(doc.body.startsWith("Redanian goulash"))
        assertTrue(doc.body.endsWith("buckwheat groats."))
    }

    @Test
    fun `ignores unknown frontmatter keys and strips quotes`() {
        val raw = """
            ---
            title: "Novigrad"
            category: 'locations'
            author: someone
            ---

            Body.
        """.trimIndent()

        val doc = MarkdownParser.parse(raw)

        assertEquals("Novigrad", doc.title)
        assertEquals("locations", doc.category)
        assertEquals("Body.", doc.body)
    }

    @Test
    fun `handles CRLF line endings`() {
        val raw = "---\r\ntitle: Vizima\r\ncategory: locations\r\n---\r\n\r\nLake city.\r\n"
        val doc = MarkdownParser.parse(raw)
        assertEquals("Vizima", doc.title)
        assertEquals("locations", doc.category)
        assertEquals("Lake city.", doc.body)
    }

    @Test
    fun `throws when frontmatter fence is missing`() {
        assertFailsWith<IllegalArgumentException> {
            MarkdownParser.parse("title: Nope\n\nBody.")
        }
    }

    @Test
    fun `throws when closing fence is missing`() {
        assertFailsWith<IllegalArgumentException> {
            MarkdownParser.parse("---\ntitle: Nope\ncategory: meals\n\nBody with no close")
        }
    }

    @Test
    fun `throws when required key is missing`() {
        assertFailsWith<IllegalArgumentException> {
            MarkdownParser.parse("---\ntitle: Only Title\n---\n\nBody.")
        }
    }
}

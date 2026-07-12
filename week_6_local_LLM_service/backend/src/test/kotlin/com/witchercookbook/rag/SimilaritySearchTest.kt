package com.witchercookbook.rag

import com.witchercookbook.model.Chunk
import com.witchercookbook.model.EmbeddedChunk
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class SimilaritySearchTest {

    private fun ec(id: String, vararg v: Float) =
        EmbeddedChunk(Chunk(id, id, "meals", "body"), floatArrayOf(*v))

    private fun searchOver(vararg chunks: EmbeddedChunk) =
        SimilaritySearch(VectorIndex.of(chunks.toList()))

    @Test
    fun `ranks nearest chunks by cosine, highest first`() {
        val search = searchOver(
            ec("east", 0f, 1f),
            ec("northeast", 1f, 1f),
            ec("north", 1f, 0f),
        )
        // Query points due north; expect north, then northeast, then east.
        val results = search.search(floatArrayOf(1f, 0f), topK = 3)

        assertEquals(listOf("north", "northeast", "east"), results.map { it.chunk.id })
        assertEquals(1.0, results[0].score, 1e-6)
        assertTrue(results[0].score > results[1].score && results[1].score > results[2].score)
    }

    @Test
    fun `cosine ignores magnitude`() {
        val search = searchOver(ec("unit", 1f, 0f), ec("far", 100f, 0f))
        val results = search.search(floatArrayOf(5f, 0f), topK = 2)

        // Same direction, different lengths -> identical score, input order kept on tie.
        assertEquals(listOf("unit", "far"), results.map { it.chunk.id })
        assertEquals(results[0].score, results[1].score, 1e-6)
    }

    @Test
    fun `truncates to topK`() {
        val search = searchOver(ec("a", 1f, 0f), ec("b", 0f, 1f), ec("c", 1f, 1f))
        assertEquals(2, search.search(floatArrayOf(1f, 0f), topK = 2).size)
    }

    @Test
    fun `returns all when topK exceeds size`() {
        val search = searchOver(ec("a", 1f, 0f), ec("b", 0f, 1f))
        assertEquals(2, search.search(floatArrayOf(1f, 0f), topK = 10).size)
    }

    @Test
    fun `topK of zero or less yields empty`() {
        val search = searchOver(ec("a", 1f, 0f))
        assertTrue(search.search(floatArrayOf(1f, 0f), topK = 0).isEmpty())
        assertTrue(search.search(floatArrayOf(1f, 0f), topK = -1).isEmpty())
    }

    @Test
    fun `empty index yields empty results`() {
        val search = SimilaritySearch(VectorIndex.of(emptyList()))
        assertTrue(search.search(floatArrayOf(1f, 0f), topK = 5).isEmpty())
    }

    @Test
    fun `rejects a query of the wrong dimension`() {
        val search = searchOver(ec("a", 1f, 0f, 0f))
        assertFailsWith<IllegalArgumentException> {
            search.search(floatArrayOf(1f, 0f), topK = 1)
        }
    }

    @Test
    fun `index reports size and dim`() {
        val index = VectorIndex.of(listOf(ec("a", 1f, 0f, 0f), ec("b", 0f, 1f, 0f)))
        assertEquals(2, index.size)
        assertEquals(3, index.dim)
    }
}

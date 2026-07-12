package com.witchercookbook.rag

import com.witchercookbook.model.Chunk
import com.witchercookbook.model.EmbeddedChunk
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class IndexCodecTest {

    private fun ec(id: String, vararg v: Float) =
        EmbeddedChunk(Chunk(id, "Title $id", "meals", "Body of $id"), floatArrayOf(*v))

    private fun roundTrip(dim: Int, chunks: List<EmbeddedChunk>): List<EmbeddedChunk> {
        val bytes = ByteArrayOutputStream().also { IndexCodec.write(it, dim, chunks) }.toByteArray()
        return IndexCodec.read(ByteArrayInputStream(bytes))
    }

    @Test
    fun `round-trips chunks and vectors identically`() {
        val chunks = listOf(
            ec("meals/goulash#0", 0.1f, -0.2f, 0.3f),
            ec("meals/goulash#1", -1.5f, 2.0f, 0.0f),
            ec("drinks/mead#0", 0.0f, 0.0f, 1.0f),
        )
        assertEquals(chunks, roundTrip(dim = 3, chunks))
    }

    @Test
    fun `round-trips an empty index`() {
        assertTrue(roundTrip(dim = 768, chunks = emptyList()).isEmpty())
    }

    @Test
    fun `preserves non-ASCII utf8 metadata and text`() {
        val chunk = EmbeddedChunk(
            Chunk("meals/żurek#0", "Żurek — сытный", "meals", "Кислый суп with świnka."),
            floatArrayOf(0.5f, 0.5f),
        )
        assertEquals(chunk, roundTrip(dim = 2, listOf(chunk)).single())
    }

    @Test
    fun `preserves special float values`() {
        val chunk = ec("x#0", Float.MAX_VALUE, -Float.MAX_VALUE, Float.MIN_VALUE, 0.0f)
        assertEquals(chunk, roundTrip(dim = 4, listOf(chunk)).single())
    }

    @Test
    fun `write rejects a vector whose length differs from dim`() {
        val bad = ec("x#0", 1.0f, 2.0f) // length 2
        assertFailsWith<IllegalArgumentException> {
            IndexCodec.write(ByteArrayOutputStream(), dim = 3, listOf(bad))
        }
    }

    @Test
    fun `write rejects an out-of-range dim`() {
        assertFailsWith<IllegalArgumentException> {
            IndexCodec.write(ByteArrayOutputStream(), dim = 0, emptyList())
        }
    }

    @Test
    fun `read fails fast on a bad magic header`() {
        val junk = byteArrayOf('N'.code.toByte(), 'O'.code.toByte(), 'P'.code.toByte(), 'E'.code.toByte(), 0, 1)
        val e = assertFailsWith<IndexFormatException> { IndexCodec.read(ByteArrayInputStream(junk)) }
        assertTrue("magic" in e.message!!)
    }

    @Test
    fun `read fails fast on a version mismatch`() {
        val bytes = ByteArrayOutputStream().also { IndexCodec.write(it, dim = 2, listOf(ec("x#0", 1f, 2f))) }.toByteArray()
        // Header: 4 magic bytes, then version u16 at offset 4..5. Bump it.
        bytes[5] = (IndexCodec.VERSION + 1).toByte()
        val e = assertFailsWith<IndexFormatException> { IndexCodec.read(ByteArrayInputStream(bytes)) }
        assertTrue("version" in e.message!!)
    }

    @Test
    fun `read fails fast on a truncated stream`() {
        val bytes = ByteArrayOutputStream().also {
            IndexCodec.write(it, dim = 3, listOf(ec("x#0", 1f, 2f, 3f)))
        }.toByteArray()
        val truncated = bytes.copyOf(bytes.size - 4) // drop the last float
        assertFailsWith<IndexFormatException> { IndexCodec.read(ByteArrayInputStream(truncated)) }
    }

    @Test
    fun `read fails fast on an empty stream`() {
        assertFailsWith<IndexFormatException> { IndexCodec.read(ByteArrayInputStream(ByteArray(0))) }
    }
}

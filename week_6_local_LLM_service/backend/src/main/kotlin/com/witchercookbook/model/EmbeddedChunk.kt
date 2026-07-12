package com.witchercookbook.model

/**
 * A [Chunk] paired with its embedding vector.
 *
 * Produced offline (chunk → embed) and serialized into the binary index by
 * `rag.IndexCodec`. At query time the server loads these back into memory for
 * cosine search. The vector length equals the index's declared embedding
 * dimension; vectors may be L2-normalized by the caller at build time so online
 * search reduces to a dot product.
 */
data class EmbeddedChunk(
    val chunk: Chunk,
    val vector: FloatArray,
) {
    // FloatArray uses identity equality by default; compare by content so round-trips
    // and tests behave like a value type.
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is EmbeddedChunk) return false
        return chunk == other.chunk && vector.contentEquals(other.vector)
    }

    override fun hashCode(): Int = 31 * chunk.hashCode() + vector.contentHashCode()
}

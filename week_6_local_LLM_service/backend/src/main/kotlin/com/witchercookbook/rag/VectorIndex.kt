package com.witchercookbook.rag

import com.witchercookbook.model.Chunk
import com.witchercookbook.model.EmbeddedChunk
import com.witchercookbook.util.VectorMath
import java.io.File

/**
 * In-memory vector index: chunk metadata alongside L2-normalized embedding vectors.
 *
 * Loaded once at startup from the binary index (spec FR-7) and never mutated. Storing
 * unit vectors lets cosine search reduce to a plain dot product (see [SimilaritySearch]).
 * Belongs to `rag`: no Ollama, no HTTP (spec §6.2).
 *
 * @property dim embedding dimension shared by every entry (0 for an empty index).
 */
class VectorIndex private constructor(val entries: List<Entry>) {

    /** A single indexed chunk with its precomputed unit vector. */
    class Entry(val chunk: Chunk, val unitVector: FloatArray)

    val size: Int get() = entries.size
    val dim: Int get() = entries.firstOrNull()?.unitVector?.size ?: 0

    companion object {
        /** Builds an index from embedded chunks, normalizing each vector once. */
        fun of(embedded: List<EmbeddedChunk>): VectorIndex =
            VectorIndex(embedded.map { Entry(it.chunk, VectorMath.normalized(it.vector)) })

        /** Loads and builds an index from a binary index file (via [IndexCodec]). */
        fun load(file: File): VectorIndex = of(IndexCodec.read(file))
    }
}

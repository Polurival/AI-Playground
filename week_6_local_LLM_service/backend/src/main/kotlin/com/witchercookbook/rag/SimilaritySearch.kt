package com.witchercookbook.rag

import com.witchercookbook.model.RetrievalResult
import com.witchercookbook.util.VectorMath

/**
 * Top-K cosine similarity search over an in-memory [VectorIndex].
 *
 * Because the index holds unit vectors, similarity is the dot product of the
 * normalized query with each entry. Pure and Ollama-free (spec §6.2, NFR-5); the
 * only embedding it needs — the query vector — is supplied by the caller.
 */
class SimilaritySearch(private val index: VectorIndex) {

    /**
     * Returns the [topK] chunks most similar to [query], highest score first.
     *
     * Ties keep index order (stable sort). Returns fewer than [topK] when the index is
     * smaller, and an empty list when [topK] <= 0 or the index is empty.
     *
     * @param query raw (un-normalized) query embedding; must match the index dimension.
     */
    fun search(query: FloatArray, topK: Int): List<RetrievalResult> {
        if (topK <= 0 || index.size == 0) return emptyList()
        require(query.size == index.dim) {
            "query dim ${query.size} != index dim ${index.dim}"
        }

        val unitQuery = VectorMath.normalized(query)
        return index.entries
            .map { RetrievalResult(it.chunk, VectorMath.dot(unitQuery, it.unitVector)) }
            .sortedByDescending { it.score }
            .take(topK)
    }
}

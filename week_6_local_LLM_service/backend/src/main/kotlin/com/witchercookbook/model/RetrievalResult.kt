package com.witchercookbook.model

/**
 * One retrieved chunk with its similarity [score] against the query (spec §8).
 *
 * Produced by cosine search and consumed by the service to pick the grounded vs
 * refusal path and to build `sources`. Score is cosine similarity in [-1, 1];
 * higher is closer.
 */
data class RetrievalResult(
    val chunk: Chunk,
    val score: Double,
)

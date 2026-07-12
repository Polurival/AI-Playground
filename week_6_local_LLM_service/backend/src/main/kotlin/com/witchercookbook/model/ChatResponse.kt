package com.witchercookbook.model

/**
 * A knowledge-base chunk that grounded (or was suggested for) the reply.
 *
 * Surfaced to the client so the user can see what the answer was based on.
 *
 * @property title source document title.
 * @property score cosine similarity of the query against that chunk, in [-1, 1].
 */
data class Source(
    val title: String,
    val score: Double,
)

/**
 * A chat response in domain terms: the assistant's generated reply plus the
 * retrieval [sources] that grounded it (empty only if nothing was retrieved).
 */
data class ChatResponse(
    val reply: String,
    val sources: List<Source> = emptyList(),
)

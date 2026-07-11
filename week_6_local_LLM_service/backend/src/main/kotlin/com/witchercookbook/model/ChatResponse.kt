package com.witchercookbook.model

/**
 * A chat response in domain terms: the assistant's generated reply.
 *
 * Grounding `sources` are added in Phase D once RAG is wired in.
 */
data class ChatResponse(
    val reply: String,
)

package com.witchercookbook.llm

/**
 * Produces an embedding vector for a piece of text.
 *
 * Kept separate from [OllamaClient] so `rag` can depend on this abstraction
 * without depending on the Ollama transport (spec §6.2).
 *
 * Split into query/document methods because `nomic-embed-text` is trained with
 * task-specific prefixes ("search_query: " / "search_document: "): embedding a
 * short query and a long chunk the same way measurably weakens their cosine
 * similarity, even for an exact-title match.
 */
interface Embedder {
    /** Embeds a user query, for searching the index. */
    suspend fun embedQuery(text: String): FloatArray

    /** Embeds a knowledge-base chunk, for building the index. */
    suspend fun embedDocument(text: String): FloatArray
}

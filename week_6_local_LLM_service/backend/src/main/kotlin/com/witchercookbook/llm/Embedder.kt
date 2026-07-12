package com.witchercookbook.llm

/**
 * Produces an embedding vector for a piece of text.
 *
 * Kept separate from [OllamaClient] so `rag` can depend on this abstraction
 * without depending on the Ollama transport (spec §6.2).
 */
interface Embedder {
    suspend fun embed(text: String): FloatArray
}

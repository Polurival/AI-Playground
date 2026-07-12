package com.witchercookbook.llm

/** [Embedder] backed by a live [OllamaClient] (e.g. `nomic-embed-text`). */
class OllamaEmbedder(private val client: OllamaClient) : Embedder {
    override suspend fun embed(text: String): FloatArray = client.embed(text)
}

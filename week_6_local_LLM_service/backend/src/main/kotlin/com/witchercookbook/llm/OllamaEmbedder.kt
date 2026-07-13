package com.witchercookbook.llm

/** [Embedder] backed by a live [OllamaClient] (e.g. `nomic-embed-text`). */
class OllamaEmbedder(private val client: OllamaClient) : Embedder {
    override suspend fun embedQuery(text: String): FloatArray = client.embed("search_query: $text")
    override suspend fun embedDocument(text: String): FloatArray = client.embed("search_document: $text")
}

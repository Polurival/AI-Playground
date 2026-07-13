package com.witchercookbook.llm

import com.witchercookbook.config.AppConfig
import kotlinx.coroutines.runBlocking

/**
 * Manual harness for [Embedder] (Task C3 verification).
 *
 * Run with a live Ollama:
 *   ./gradlew embedHarness -Ptext="venison stew"
 *
 * Not part of the server; exists only to eyeball a real embedding vector.
 */
fun main(args: Array<String>) = runBlocking {
    val text = args.firstOrNull() ?: "venison stew"
    val config = AppConfig.load()

    println("→ Ollama: ${config.ollamaUrl}  model: ${config.embedModel}")
    println("→ Text: $text")

    OllamaClient(config).use { client ->
        val embedder: Embedder = OllamaEmbedder(client)
        val vector = embedder.embedQuery(text)
        println("← Dim: ${vector.size}")
        println("← First values: ${vector.take(5)}")
    }
}

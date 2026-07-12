package com.witchercookbook.llm

import com.witchercookbook.config.AppConfig
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.runBlocking

/**
 * Manual harness for [OllamaClient.chatStream] (Task E1 verification).
 *
 * Run with a live Ollama:
 *   ./gradlew streamHarness -Pprompt="Say hi"
 *
 * Prints each content delta the instant it arrives (no newline, flushed) so the
 * incremental nature of the stream is visible. Not part of the server.
 */
fun main(args: Array<String>) = runBlocking {
    val prompt = args.firstOrNull() ?: "Say hi"
    val config = AppConfig.load()

    println("→ Ollama: ${config.ollamaUrl}  model: ${config.chatModel}")
    println("→ Prompt: $prompt")
    print("← Reply: ")

    OllamaClient(config).use { client ->
        client.chatStream(prompt).collect { delta ->
            print(delta)
            System.out.flush()
        }
    }
    println()
}

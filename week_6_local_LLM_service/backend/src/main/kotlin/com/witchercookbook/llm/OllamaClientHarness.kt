package com.witchercookbook.llm

import com.witchercookbook.config.AppConfig
import kotlinx.coroutines.runBlocking

/**
 * Manual harness for [OllamaClient] (Task A3 verification).
 *
 * Run with a live Ollama:
 *   ./gradlew chatHarness -Pprompt="Say hi"
 *
 * Not part of the server; exists only to eyeball a real completion.
 */
fun main(args: Array<String>) = runBlocking {
    val prompt = args.firstOrNull() ?: "Say hi"
    val config = AppConfig.load()

    println("→ Ollama: ${config.ollamaUrl}  model: ${config.chatModel}")
    println("→ Prompt: $prompt")

    OllamaClient(config).use { client ->
        val reply = client.chat(prompt)
        println("← Reply:\n$reply")
    }
}

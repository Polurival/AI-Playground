package com.witchercookbook

import com.witchercookbook.config.AppConfig
import com.witchercookbook.controller.RateLimiter
import com.witchercookbook.controller.chatRoutes
import com.witchercookbook.controller.healthRoutes
import com.witchercookbook.llm.LlmConcurrencyGate
import com.witchercookbook.llm.OllamaClient
import com.witchercookbook.rag.VectorIndex
import com.witchercookbook.service.ChatService
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.Application
import io.ktor.server.application.install
import io.ktor.server.engine.embeddedServer
import io.ktor.server.netty.Netty
import io.ktor.server.plugins.calllogging.CallLogging
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.routing.routing
import kotlinx.serialization.json.Json
import java.io.File

fun main() {
    val config = AppConfig.load()
    embeddedServer(Netty, port = config.serverPort, host = "0.0.0.0") {
        module(config)
    }.start(wait = true)
}

fun Application.module(config: AppConfig = AppConfig.load()) {
    install(ContentNegotiation) {
        json(Json { prettyPrint = false; ignoreUnknownKeys = true })
    }
    install(CallLogging)

    val vectorIndex = loadVectorIndex(config)
    val ollama = OllamaClient(config)
    val gate = LlmConcurrencyGate(
        maxConcurrent = config.llmMaxConcurrent,
        maxQueue = config.llmMaxQueue,
    )
    val chatService = ChatService(ollama, gate)
    val rateLimiter = RateLimiter(
        capacity = config.rateLimitCapacity,
        refillPerMinute = config.rateLimitRefillPerMinute,
    )

    routing {
        healthRoutes(vectorIndex)
        chatRoutes(chatService, config, rateLimiter)
    }
}

/** Loads the offline-built index (spec §11). Fails fast: the server never embeds the KB itself. */
private fun loadVectorIndex(config: AppConfig): VectorIndex {
    val file = File(config.indexPath)
    if (!file.exists()) {
        throw IllegalStateException(
            "Index file not found at '${config.indexPath}'. Run the indexer (./gradlew indexer) before starting the server."
        )
    }
    return VectorIndex.load(file)
}

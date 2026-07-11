package com.witchercookbook

import com.witchercookbook.config.AppConfig
import com.witchercookbook.controller.chatRoutes
import com.witchercookbook.controller.healthRoutes
import com.witchercookbook.llm.OllamaClient
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

    val ollama = OllamaClient(config)
    val chatService = ChatService(ollama)

    routing {
        healthRoutes()
        chatRoutes(chatService, config)
    }
}

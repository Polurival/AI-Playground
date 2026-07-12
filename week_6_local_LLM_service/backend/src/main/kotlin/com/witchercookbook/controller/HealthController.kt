package com.witchercookbook.controller

import com.witchercookbook.rag.VectorIndex
import io.ktor.server.response.respond
import io.ktor.server.routing.Route
import io.ktor.server.routing.get
import kotlinx.serialization.Serializable

@Serializable
data class HealthResponse(val status: String, val indexLoaded: Boolean, val chunks: Int)

fun Route.healthRoutes(vectorIndex: VectorIndex) {
    get("/api/health") {
        call.respond(HealthResponse(status = "ok", indexLoaded = true, chunks = vectorIndex.size))
    }
}

package com.witchercookbook.controller

import com.witchercookbook.config.AppConfig
import com.witchercookbook.llm.LlmBusyException
import com.witchercookbook.llm.OllamaException
import com.witchercookbook.model.ChatRequest
import com.witchercookbook.model.Message
import com.witchercookbook.model.Role
import com.witchercookbook.service.ChatService
import com.witchercookbook.service.StreamingChat
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.ApplicationCall
import io.ktor.server.plugins.origin
import io.ktor.server.request.receive
import io.ktor.server.response.header
import io.ktor.server.response.respond
import io.ktor.server.response.respondTextWriter
import io.ktor.server.routing.Route
import io.ktor.server.routing.RoutingContext
import io.ktor.server.routing.post
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.slf4j.LoggerFactory
import java.io.Writer

private val logger = LoggerFactory.getLogger("com.witchercookbook.controller.ChatController")

/**
 * Wire DTOs and routing for `POST /api/chat`.
 *
 * The controller is the only place that knows both HTTP/JSON and the domain: it
 * receives [ChatRequestDto], maps it onto the domain [ChatRequest], delegates to
 * [ChatService], and maps the result back to [ChatResponseDto]. No HTTP or JSON
 * types cross into the service.
 */

@Serializable
data class MessageDto(
    val role: String,
    val content: String,
)

@Serializable
data class ChatRequestDto(
    val messages: List<MessageDto>,
    /** When true, the reply is streamed back as Server-Sent Events instead of one JSON body. */
    val stream: Boolean = false,
)

@Serializable
data class SourceDto(
    val title: String,
    val score: Double,
)

@Serializable
data class ChatResponseDto(
    val reply: String,
    val sources: List<SourceDto> = emptyList(),
)

@Serializable
data class ErrorBody(
    val code: String,
    val message: String,
)

@Serializable
data class ErrorDto(
    val error: ErrorBody,
)

private fun errorDto(code: String, message: String) = ErrorDto(ErrorBody(code, message))

fun Route.chatRoutes(service: ChatService, config: AppConfig, rateLimiter: RateLimiter) {
    post("/api/chat") {
        val clientIp = call.clientIp()
        when (val decision = rateLimiter.check(clientIp)) {
            is RateLimiter.Decision.Allowed -> Unit
            is RateLimiter.Decision.Limited -> {
                logger.warn("rate limit hit clientIp={} retryAfterSeconds={}", clientIp, decision.retryAfterSeconds)
                call.response.header(HttpHeaders.RetryAfter, decision.retryAfterSeconds.toString())
                call.respond(
                    HttpStatusCode.TooManyRequests,
                    errorDto("RATE_LIMITED", "Rate limit exceeded; retry after ${decision.retryAfterSeconds}s"),
                )
                return@post
            }
        }

        val dto = call.receive<ChatRequestDto>()

        try {
            dto.enforceMaxContext(config)
        } catch (e: ContextTooLargeException) {
            call.respond(
                HttpStatusCode.PayloadTooLarge,
                errorDto("CONTEXT_TOO_LARGE", e.message ?: "Request exceeds max context"),
            )
            return@post
        }

        val domain = try {
            dto.toDomain()
        } catch (e: IllegalArgumentException) {
            call.respond(HttpStatusCode.BadRequest, errorDto("VALIDATION_ERROR", e.message ?: "Invalid request"))
            return@post
        }

        if (dto.stream) {
            respondChatStream(service, domain)
            return@post
        }

        try {
            val response = service.chat(domain)
            call.respond(
                ChatResponseDto(
                    reply = response.reply,
                    sources = response.sources.map { SourceDto(it.title, it.score) },
                )
            )
        } catch (e: IllegalArgumentException) {
            call.respond(HttpStatusCode.BadRequest, errorDto("VALIDATION_ERROR", e.message ?: "Invalid request"))
        } catch (e: LlmBusyException) {
            // Concurrency gate saturated: shed load cleanly and invite a retry.
            call.response.header(HttpHeaders.RetryAfter, "1")
            call.respond(HttpStatusCode.ServiceUnavailable, errorDto("LLM_UNAVAILABLE", e.message ?: "LLM busy"))
        } catch (e: OllamaException) {
            call.respond(HttpStatusCode.BadGateway, errorDto("LLM_UNAVAILABLE", e.message ?: "LLM error"))
        }
    }
}

// Shared Json for SSE payloads; each event's `data:` line is a compact JSON value.
private val sseJson = Json { encodeDefaults = false }

/**
 * Streams a chat reply as Server-Sent Events.
 *
 * Retrieval runs first so pre-stream failures (empty request, embedding/index
 * errors, a saturated gate) still map to a normal JSON error status. Once the
 * event stream has started we are committed to `200 text/event-stream`, so any
 * failure while generating tokens is delivered as an `error` event instead.
 *
 * Event protocol (each frame is `event: <name>` + a single JSON `data:` line):
 *   - `token`   — a content delta (JSON-encoded string)
 *   - `sources` — the grounding sources (JSON array), sent once after the tokens
 *   - `done`    — terminal marker
 *   - `error`   — `{code,message}` if generation fails mid-stream
 */
private suspend fun RoutingContext.respondChatStream(service: ChatService, domain: ChatRequest) {
    val streaming: StreamingChat = try {
        service.chatStream(domain)
    } catch (e: IllegalArgumentException) {
        call.respond(HttpStatusCode.BadRequest, errorDto("VALIDATION_ERROR", e.message ?: "Invalid request"))
        return
    } catch (e: LlmBusyException) {
        call.response.header(HttpHeaders.RetryAfter, "1")
        call.respond(HttpStatusCode.ServiceUnavailable, errorDto("LLM_UNAVAILABLE", e.message ?: "LLM busy"))
        return
    } catch (e: OllamaException) {
        call.respond(HttpStatusCode.BadGateway, errorDto("LLM_UNAVAILABLE", e.message ?: "LLM error"))
        return
    }

    // Defeat proxy buffering so tokens reach the browser as they are written.
    call.response.header(HttpHeaders.CacheControl, "no-cache")
    call.response.header("X-Accel-Buffering", "no")
    call.respondTextWriter(ContentType.Text.EventStream) {
        try {
            streaming.tokens.collect { token ->
                writeEvent("token", sseJson.encodeToString(token))
            }
            val sources = streaming.sources.map { SourceDto(it.title, it.score) }
            writeEvent("sources", sseJson.encodeToString(sources))
            writeEvent("done", "{}")
        } catch (e: LlmBusyException) {
            writeEvent("error", sseJson.encodeToString(ErrorBody("LLM_UNAVAILABLE", e.message ?: "LLM busy")))
        } catch (e: OllamaException) {
            writeEvent("error", sseJson.encodeToString(ErrorBody("LLM_UNAVAILABLE", e.message ?: "LLM error")))
        }
    }
}

/** Writes one SSE frame and flushes so the client receives it immediately. */
private fun Writer.writeEvent(event: String, data: String) {
    write("event: $event\n")
    write("data: $data\n\n")
    flush()
}

private fun ChatRequestDto.toDomain(): ChatRequest {
    require(messages.isNotEmpty()) { "messages must not be empty" }
    return ChatRequest(messages = messages.map { it.toDomain() })
}

private fun MessageDto.toDomain(): Message {
    require(content.isNotBlank()) { "message content must not be blank" }
    return Message(role = role.toRole(), content = content)
}

/**
 * Resolves the originating client IP for rate limiting.
 *
 * Behind Nginx the socket peer is always localhost, so the real client is the
 * first entry of `X-Forwarded-For` (the closest untrusted hop). Falls back to
 * the direct socket address for local/direct requests.
 */
private fun ApplicationCall.clientIp(): String =
    request.headers["X-Forwarded-For"]
        ?.split(',')
        ?.firstOrNull()
        ?.trim()
        ?.takeIf { it.isNotEmpty() }
        ?: request.origin.remoteHost

private fun String.toRole(): Role = when (lowercase()) {
    "user" -> Role.USER
    "assistant" -> Role.ASSISTANT
    "system" -> Role.SYSTEM
    else -> throw IllegalArgumentException("Unknown role: '$this'")
}

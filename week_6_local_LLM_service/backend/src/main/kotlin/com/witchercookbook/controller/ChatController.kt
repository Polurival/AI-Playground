package com.witchercookbook.controller

import com.witchercookbook.config.AppConfig
import com.witchercookbook.llm.LlmBusyException
import com.witchercookbook.llm.OllamaException
import com.witchercookbook.model.ChatRequest
import com.witchercookbook.model.Message
import com.witchercookbook.model.Role
import com.witchercookbook.service.ChatService
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.ApplicationCall
import io.ktor.server.plugins.origin
import io.ktor.server.request.receive
import io.ktor.server.response.header
import io.ktor.server.response.respond
import io.ktor.server.routing.Route
import io.ktor.server.routing.post
import kotlinx.serialization.Serializable

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
)

@Serializable
data class ChatResponseDto(
    val reply: String,
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
        when (val decision = rateLimiter.check(call.clientIp())) {
            is RateLimiter.Decision.Allowed -> Unit
            is RateLimiter.Decision.Limited -> {
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

        try {
            val response = service.chat(domain)
            call.respond(ChatResponseDto(reply = response.reply))
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

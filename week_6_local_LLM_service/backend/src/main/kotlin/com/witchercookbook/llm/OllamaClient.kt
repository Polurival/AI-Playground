package com.witchercookbook.llm

import com.witchercookbook.config.AppConfig
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpRequestRetry
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString

/**
 * Thin, non-streaming client for a local Ollama server.
 *
 * Owns its own [HttpClient] with timeouts and basic retry. Talks only in Ollama
 * wire DTOs and returns the plain assistant text — no prompt assembly, no domain
 * types, no HTTP concepts leak to callers.
 *
 * Call [close] when done (or use it via [use]).
 */
class OllamaClient(
    private val baseUrl: String,
    private val model: String,
    private val embedModel: String,
    private val client: HttpClient = defaultClient(),
) : AutoCloseable {

    constructor(config: AppConfig, client: HttpClient = defaultClient()) :
        this(baseUrl = config.ollamaUrl, model = config.chatModel, embedModel = config.embedModel, client = client)

    /** Convenience overload for a single user turn. */
    suspend fun chat(prompt: String): String =
        chat(listOf(OllamaChatMessage(role = "user", content = prompt)))

    /**
     * Sends [messages] to Ollama and returns the assistant's completed reply.
     *
     * @throws OllamaException if the server errors or returns no message content.
     */
    suspend fun chat(messages: List<OllamaChatMessage>): String {
        val request = OllamaChatRequest(
            model = model,
            messages = messages,
            stream = false,
            // think=true makes Ollama put qwen3's reasoning in a separate `thinking`
            // field, leaving `message.content` clean. think=false bleeds reasoning
            // into content, so keep it enabled and simply ignore `thinking`.
            think = true,
        )

        val response: HttpResponse = try {
            client.post("$baseUrl/api/chat") {
                contentType(ContentType.Application.Json)
                setBody(json.encodeToString(request))
            }
        } catch (e: Exception) {
            throw OllamaException("Failed to reach Ollama at $baseUrl: ${e.message}", e)
        }

        val text = response.bodyAsText()
        if (!response.status.isSuccess()) {
            throw OllamaException("Ollama returned ${response.status} for model '$model': $text")
        }

        val body = try {
            json.decodeFromString<OllamaChatResponse>(text)
        } catch (e: Exception) {
            throw OllamaException("Failed to parse Ollama response: ${e.message}", e)
        }
        return body.message?.content
            ?: throw OllamaException("Ollama response contained no message content")
    }

    /**
     * Embeds [text] via Ollama's embeddings endpoint using [embedModel].
     *
     * @throws OllamaException if the server errors or returns an empty vector.
     */
    suspend fun embed(input: String): FloatArray {
        val request = OllamaEmbeddingRequest(model = embedModel, prompt = input)

        val response: HttpResponse = try {
            client.post("$baseUrl/api/embeddings") {
                contentType(ContentType.Application.Json)
                setBody(json.encodeToString(request))
            }
        } catch (e: Exception) {
            throw OllamaException("Failed to reach Ollama at $baseUrl: ${e.message}", e)
        }

        val text = response.bodyAsText()
        if (!response.status.isSuccess()) {
            throw OllamaException("Ollama returned ${response.status} for model '$embedModel': $text")
        }

        val body = try {
            json.decodeFromString<OllamaEmbeddingResponse>(text)
        } catch (e: Exception) {
            throw OllamaException("Failed to parse Ollama embedding response: ${e.message}", e)
        }
        if (body.embedding.isEmpty()) {
            throw OllamaException("Ollama embedding response contained no vector")
        }
        return body.embedding.toFloatArray()
    }

    override fun close() = client.close()

    companion object {
        // encodeDefaults=true is required so `stream=false` is actually sent;
        // otherwise Ollama defaults to streaming and returns NDJSON.
        private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

        /** Builds the default engine: 30s connect, generous request timeout, 2 retries. */
        fun defaultClient(): HttpClient = HttpClient(CIO) {
            expectSuccess = false
            install(HttpTimeout) {
                connectTimeoutMillis = 30_000
                requestTimeoutMillis = 300_000
                socketTimeoutMillis = 300_000
            }
            install(HttpRequestRetry) {
                retryOnExceptionOrServerErrors(maxRetries = 2)
                exponentialDelay()
            }
        }
    }
}

/** Raised when the Ollama call fails or returns an unusable response. */
class OllamaException(message: String, cause: Throwable? = null) : RuntimeException(message, cause)

package com.witchercookbook.llm

import com.witchercookbook.config.AppConfig
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpRequestRetry
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.request.post
import io.ktor.client.request.preparePost
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsChannel
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
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

    /** Convenience overload for a single user turn. */
    fun chatStream(prompt: String): Flow<String> =
        chatStream(listOf(OllamaChatMessage(role = "user", content = prompt)))

    /**
     * Streams the assistant's reply for [messages] as a cold [Flow] of content
     * deltas, in arrival order. Collect it to drive the tokens somewhere.
     *
     * Ollama answers `stream=true` with NDJSON: one [OllamaChatResponse] per line,
     * each carrying an incremental `message.content`. Reasoning tokens land in the
     * ignored `thinking` field, so only non-empty content is emitted. The flow
     * completes when Ollama sends `done=true` (or the stream ends).
     *
     * The underlying HTTP response stays open only while the flow is being
     * collected; cancelling the collector closes it. The non-streaming [chat] path
     * is unaffected.
     *
     * @throws OllamaException if the server errors or a line fails to parse.
     */
    fun chatStream(messages: List<OllamaChatMessage>): Flow<String> = flow {
        val request = OllamaChatRequest(
            model = model,
            messages = messages,
            stream = true,
            think = true,
        )

        try {
            client.preparePost("$baseUrl/api/chat") {
                contentType(ContentType.Application.Json)
                setBody(json.encodeToString(request))
            }.execute { response ->
                if (!response.status.isSuccess()) {
                    throw OllamaException(
                        "Ollama returned ${response.status} for model '$model': ${response.bodyAsText()}"
                    )
                }
                val channel = response.bodyAsChannel()
                while (true) {
                    val line = channel.readUTF8Line() ?: break
                    if (line.isBlank()) continue
                    val chunk = try {
                        json.decodeFromString<OllamaChatResponse>(line)
                    } catch (e: Exception) {
                        throw OllamaException("Failed to parse Ollama stream line: ${e.message}", e)
                    }
                    chunk.message?.content?.takeIf { it.isNotEmpty() }?.let { emit(it) }
                    if (chunk.done) break
                }
            }
        } catch (e: OllamaException) {
            throw e
        } catch (e: Exception) {
            throw OllamaException("Failed to reach Ollama at $baseUrl: ${e.message}", e)
        }
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

        /**
         * Builds the default engine: 30s connect, generous request/socket timeout
         * (CPU-only inference can take minutes to produce a first token), 2 retries.
         */
        fun defaultClient(): HttpClient = HttpClient(CIO) {
            expectSuccess = false
            install(HttpTimeout) {
                connectTimeoutMillis = 30_000
                requestTimeoutMillis = 600_000
                socketTimeoutMillis = 600_000
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

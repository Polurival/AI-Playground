package com.witchercookbook.service

import com.witchercookbook.llm.Embedder
import com.witchercookbook.llm.LlmConcurrencyGate
import com.witchercookbook.llm.OllamaChatMessage
import com.witchercookbook.llm.OllamaClient
import com.witchercookbook.model.ChatRequest
import com.witchercookbook.model.ChatResponse
import com.witchercookbook.model.Message
import com.witchercookbook.model.RetrievalResult
import com.witchercookbook.model.Role
import com.witchercookbook.model.Source
import com.witchercookbook.prompt.PromptBuilder
import com.witchercookbook.prompt.PromptMode
import com.witchercookbook.rag.SimilaritySearch
import com.witchercookbook.util.LanguageDetector
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.onCompletion
import kotlin.time.measureTimedValue
import org.slf4j.LoggerFactory

/**
 * Orchestrates a grounded chat turn — the point where every RAG boundary meets
 * (spec §10). Depends only on the domain [model], the `rag` retrieval, the
 * `prompt` builder, and the `llm` layer — never on Ktor/HTTP.
 *
 * Pipeline: detect the query language → embed the query → cosine-search the index
 * → compare the top score to [relevanceMinScore] to choose the grounded vs
 * refusal-with-suggestion prompt → assemble the prompt ([PromptBuilder]) → call
 * Ollama. The Ollama call is fenced by [gate] so concurrent load on the local
 * model stays bounded (Phase B3); excess callers get [com.witchercookbook.llm.LlmBusyException].
 */
class ChatService(
    private val embedder: Embedder,
    private val search: SimilaritySearch,
    private val promptBuilder: PromptBuilder,
    private val ollama: OllamaClient,
    private val gate: LlmConcurrencyGate,
    private val topK: Int,
    private val relevanceMinScore: Double,
) {
    private val logger = LoggerFactory.getLogger(ChatService::class.java)

    /**
     * Runs [request] through retrieval + the LLM and returns a grounded reply.
     *
     * @throws IllegalArgumentException if the request carries no messages.
     */
    suspend fun chat(request: ChatRequest): ChatResponse {
        val prepared = prepare(request)
        val (reply, elapsed) = measureTimedValue {
            gate.withPermit { ollama.chat(prepared.prompt.map { it.toOllama() }) }
        }
        logger.info("ollama chat done latencyMs={} replyChars={}", elapsed.inWholeMilliseconds, reply.length)
        return ChatResponse(reply = reply.trim(), sources = prepared.sources)
    }

    /**
     * Streaming counterpart of [chat]. Retrieval runs eagerly (so an embedding or
     * search failure surfaces before the response starts), and the returned
     * [StreamingChat.sources] are already final. [StreamingChat.tokens] is a cold
     * flow: collecting it acquires the [gate] permit, streams Ollama's content
     * deltas, and releases the permit when the flow completes or the collector is
     * cancelled (e.g. the client disconnects).
     *
     * @throws IllegalArgumentException if the request carries no messages.
     */
    suspend fun chatStream(request: ChatRequest): StreamingChat {
        val prepared = prepare(request)
        val startMs = System.currentTimeMillis()
        var tokenCount = 0
        val tokens: Flow<String> = flow {
            gate.withPermit {
                ollama.chatStream(prepared.prompt.map { it.toOllama() }).collect {
                    tokenCount++
                    emit(it)
                }
            }
        }.onCompletion { cause ->
            val latencyMs = System.currentTimeMillis() - startMs
            if (cause == null) {
                logger.info("ollama stream done latencyMs={} tokens={}", latencyMs, tokenCount)
            } else {
                logger.warn("ollama stream aborted latencyMs={} tokens={} cause={}", latencyMs, tokenCount, cause.toString())
            }
        }
        return StreamingChat(sources = prepared.sources, tokens = tokens)
    }

    /** Retrieval + prompt assembly shared by the streaming and non-streaming paths. */
    private suspend fun prepare(request: ChatRequest): Prepared {
        require(request.messages.isNotEmpty()) { "Chat request must contain at least one message" }

        val query = latestUserQuery(request.messages)
        val language = LanguageDetector.detect(query)

        val queryVector = embedder.embed(query)
        val results = search.search(queryVector, topK)
        val mode = if (isGrounded(results)) PromptMode.GROUNDED else PromptMode.REFUSAL
        logger.info(
            "retrieval language={} mode={} topScore={} results={}",
            language, mode, results.firstOrNull()?.score, results.size,
        )

        val prompt = promptBuilder.build(mode, request.messages, results, language)
        return Prepared(prompt = prompt, sources = results.toSources())
    }

    /** The assembled prompt plus the (final) sources, ready for either path. */
    private data class Prepared(
        val prompt: List<Message>,
        val sources: List<Source>,
    )

    /** Grounded when at least one retrieved chunk clears the relevance threshold (spec §11). */
    private fun isGrounded(results: List<RetrievalResult>): Boolean =
        results.firstOrNull()?.let { it.score >= relevanceMinScore } == true

    /** The text we retrieve and detect language on: the user's most recent message. */
    private fun latestUserQuery(messages: List<Message>): String =
        (messages.lastOrNull { it.role == Role.USER } ?: messages.last()).content

    /** One source per distinct title, keeping the best (first, since results are sorted) score. */
    private fun List<RetrievalResult>.toSources(): List<Source> =
        distinctBy { it.chunk.title }.map { Source(title = it.chunk.title, score = it.score) }

    private fun Message.toOllama(): OllamaChatMessage =
        OllamaChatMessage(role = role.wire, content = content)

    private val Role.wire: String
        get() = when (this) {
            Role.USER -> "user"
            Role.ASSISTANT -> "assistant"
            Role.SYSTEM -> "system"
        }
}

/**
 * A streaming chat result: the reply arrives incrementally over [tokens] while
 * [sources] (known once retrieval completes) can be sent to the client after the
 * stream finishes.
 */
data class StreamingChat(
    val sources: List<Source>,
    val tokens: Flow<String>,
)

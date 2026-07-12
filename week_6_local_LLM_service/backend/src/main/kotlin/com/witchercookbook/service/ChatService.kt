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
    /**
     * Runs [request] through retrieval + the LLM and returns a grounded reply.
     *
     * @throws IllegalArgumentException if the request carries no messages.
     */
    suspend fun chat(request: ChatRequest): ChatResponse {
        require(request.messages.isNotEmpty()) { "Chat request must contain at least one message" }

        val query = latestUserQuery(request.messages)
        val language = LanguageDetector.detect(query)

        val queryVector = embedder.embed(query)
        val results = search.search(queryVector, topK)
        val mode = if (isGrounded(results)) PromptMode.GROUNDED else PromptMode.REFUSAL

        val prompt = promptBuilder.build(mode, request.messages, results, language)
        val reply = gate.withPermit { ollama.chat(prompt.map { it.toOllama() }) }

        return ChatResponse(reply = reply.trim(), sources = results.toSources())
    }

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

package com.witchercookbook.service

import com.witchercookbook.llm.OllamaChatMessage
import com.witchercookbook.llm.OllamaClient
import com.witchercookbook.model.ChatRequest
import com.witchercookbook.model.ChatResponse
import com.witchercookbook.model.Message
import com.witchercookbook.model.Role

/**
 * Orchestrates a chat turn: domain request in, domain response out.
 *
 * Depends only on the domain [model] and the [llm] layer — never on Ktor/HTTP.
 * For now it assembles a minimal prompt inline; in Phase D3 this responsibility
 * moves to `PromptBuilder` and RAG retrieval is added.
 */
class ChatService(
    private val ollama: OllamaClient,
) {
    /**
     * Runs [request] through the LLM and returns the assistant's reply.
     *
     * @throws IllegalArgumentException if the request carries no messages.
     */
    suspend fun chat(request: ChatRequest): ChatResponse {
        require(request.messages.isNotEmpty()) { "Chat request must contain at least one message" }

        val messages = buildList {
            add(OllamaChatMessage(role = "system", content = MINIMAL_SYSTEM_PROMPT))
            request.messages.forEach { add(it.toOllama()) }
        }

        val reply = ollama.chat(messages)
        return ChatResponse(reply = reply.trim())
    }

    private fun Message.toOllama(): OllamaChatMessage =
        OllamaChatMessage(role = role.wire, content = content)

    private val Role.wire: String
        get() = when (this) {
            Role.USER -> "user"
            Role.ASSISTANT -> "assistant"
            Role.SYSTEM -> "system"
        }

    private companion object {
        // Placeholder persona/grounding. Replaced by PromptBuilder + RAG context in Phase D.
        const val MINIMAL_SYSTEM_PROMPT =
            "You are a cook in the world of The Witcher. Answer with a single, concrete " +
                "cooking recipe: a short intro, an ingredients list, and numbered steps. " +
                "Reply in the same language as the user."
    }
}

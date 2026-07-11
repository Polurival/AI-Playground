package com.witchercookbook.controller

import com.witchercookbook.config.AppConfig

/**
 * Thrown when a chat request exceeds a configured max-context guard.
 *
 * Caught by [chatRoutes] and mapped to `413 CONTEXT_TOO_LARGE` before the
 * request reaches [com.witchercookbook.service.ChatService] or Ollama.
 */
class ContextTooLargeException(message: String) : Exception(message)

/**
 * Rejects requests that would blow the model's context window, before any
 * LLM call is made.
 *
 * Token counts aren't known until the model tokenizes the prompt, so we use
 * a coarse approximation (~4 chars/token, a common rule of thumb for English
 * text) purely as a cheap upper-bound guard, not an exact count.
 */
fun ChatRequestDto.enforceMaxContext(config: AppConfig) {
    if (messages.size > config.maxContextMessages) {
        throw ContextTooLargeException(
            "Too many messages: ${messages.size} exceeds the limit of ${config.maxContextMessages}"
        )
    }

    messages.forEachIndexed { index, message ->
        if (message.content.length > config.maxMessageChars) {
            throw ContextTooLargeException(
                "Message $index is too long: ${message.content.length} chars exceeds the limit of ${config.maxMessageChars}"
            )
        }
    }

    val approxTokens = messages.sumOf { it.content.length } / CHARS_PER_TOKEN_ESTIMATE
    if (approxTokens > config.maxContextTokens) {
        throw ContextTooLargeException(
            "Request too large: ~$approxTokens tokens exceeds the limit of ${config.maxContextTokens}"
        )
    }
}

private const val CHARS_PER_TOKEN_ESTIMATE = 4

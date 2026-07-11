package com.witchercookbook.model

/**
 * A chat request in domain terms: the full conversation history the client holds.
 *
 * The server is stateless — the client sends the whole history each time.
 */
data class ChatRequest(
    val messages: List<Message>,
)

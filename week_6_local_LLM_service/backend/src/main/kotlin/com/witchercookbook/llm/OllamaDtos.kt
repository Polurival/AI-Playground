package com.witchercookbook.llm

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire-level DTOs for Ollama's `/api/chat` endpoint.
 *
 * These mirror Ollama's JSON contract exactly and live only in the `llm` layer.
 * No prompt assembly or domain logic belongs here.
 */

/** A single chat turn as understood by Ollama. */
@Serializable
data class OllamaChatMessage(
    val role: String,
    val content: String,
)

/** Request body for `POST /api/chat`. */
@Serializable
data class OllamaChatRequest(
    val model: String,
    val messages: List<OllamaChatMessage>,
    val stream: Boolean = false,
    /** When true, qwen3's reasoning is separated into `thinking`, keeping `content` clean. */
    val think: Boolean? = null,
    val options: OllamaOptions? = null,
)

/** Generation options passed through to Ollama. */
@Serializable
data class OllamaOptions(
    val temperature: Double? = null,
    @SerialName("num_ctx") val numCtx: Int? = null,
)

/** Response body for a non-streaming `POST /api/chat`. */
@Serializable
data class OllamaChatResponse(
    val model: String? = null,
    val message: OllamaChatMessage? = null,
    val done: Boolean = false,
    @SerialName("done_reason") val doneReason: String? = null,
)

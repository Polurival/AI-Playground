package com.witchercookbook.model

/** Who authored a chat turn. Domain-level; independent of any wire format. */
enum class Role {
    USER,
    ASSISTANT,
    SYSTEM,
}

/**
 * A single conversation turn in the domain.
 *
 * Pure domain type: no serialization, no HTTP, no LLM concerns. Controllers map
 * their wire DTOs onto this; the LLM layer maps this onto its own DTOs.
 */
data class Message(
    val role: Role,
    val content: String,
)

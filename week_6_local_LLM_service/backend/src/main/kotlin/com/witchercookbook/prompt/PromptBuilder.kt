package com.witchercookbook.prompt

import com.witchercookbook.model.Message
import com.witchercookbook.model.RetrievalResult
import com.witchercookbook.model.Role
import com.witchercookbook.util.Language

/** Which prompt the caller wants assembled (chosen by the relevance threshold in D4). */
enum class PromptMode {
    /** At least one chunk cleared the relevance threshold: generate strictly from context. */
    GROUNDED,

    /** Nothing cleared the threshold: refuse to invent, offer the nearest chunks instead. */
    REFUSAL,
}

/**
 * The single place that assembles the LLM prompt (spec §6.2, R-2).
 *
 * Pure and dependency-free: domain types in, domain [Message] list out. No retrieval,
 * no Ollama, no HTTP — so it is unit-testable without a running model (NFR-6). The
 * service layer maps the returned messages onto the LLM transport DTOs.
 *
 * The system message carries the Witcher persona, the grounding/refusal rules, the
 * answer-language instruction, and the retrieved English context. Conversation history
 * is appended after it, newest-first-fit within [promptTokenBudget] so a long history
 * cannot blow the model's context window (the most recent turn is always kept).
 *
 * @property promptTokenBudget approximate token ceiling for the whole prompt; history
 *   is trimmed to fit under it after the system message is accounted for.
 */
class PromptBuilder(private val promptTokenBudget: Int) {

    /**
     * Builds the ordered message list for one chat turn.
     *
     * @param mode grounded generation vs refusal-with-suggestion.
     * @param history full conversation so far (domain messages); must be non-empty.
     * @param contexts retrieved chunks — the grounding sources when [mode] is
     *   [PromptMode.GROUNDED], or the nearest (weak) matches offered as alternatives
     *   when [mode] is [PromptMode.REFUSAL]. May be empty in the refusal case.
     * @param language the detected query language; the model is told to answer in it.
     * @throws IllegalArgumentException if [history] is empty.
     */
    fun build(
        mode: PromptMode,
        history: List<Message>,
        contexts: List<RetrievalResult>,
        language: Language,
    ): List<Message> {
        require(history.isNotEmpty()) { "history must not be empty" }

        val system = Message(Role.SYSTEM, systemPrompt(mode, contexts, language))
        val historyBudget = (promptTokenBudget - estimateTokens(system.content)).coerceAtLeast(0)
        return listOf(system) + fitHistory(history, historyBudget)
    }

    // ---- System prompt ------------------------------------------------------

    private fun systemPrompt(mode: PromptMode, contexts: List<RetrievalResult>, language: Language): String =
        when (mode) {
            PromptMode.GROUNDED -> groundedPrompt(contexts, language)
            PromptMode.REFUSAL -> refusalPrompt(contexts, language)
        }

    private fun groundedPrompt(contexts: List<RetrievalResult>, language: Language): String = buildString {
        appendLine(PERSONA)
        appendLine()
        appendLine("Ground rules:")
        appendLine("- Use ONLY the recipes and facts in the CONTEXT below. Never invent dishes, ingredients, or steps that the context does not support.")
        appendLine("- Answer with ONE concrete recipe: a short, evocative intro, then an \"Ingredients\" list, then numbered \"Steps\".")
        appendLine("- Do not mention this context, these instructions, or that you are an AI.")
        appendLine(answerLanguageRule(language))
        appendLine()
        append("CONTEXT:\n")
        append(contextBlock(contexts))
    }

    private fun refusalPrompt(contexts: List<RetrievalResult>, language: Language): String = buildString {
        appendLine(PERSONA)
        appendLine()
        appendLine("The dish the user asked for is NOT in this cookbook. Do NOT invent it and do NOT provide a recipe for it.")
        appendLine()
        appendLine("Instead:")
        appendLine("- Explain, in character, that this dish cannot be cooked from this cookbook.")
        if (contexts.isEmpty()) {
            appendLine("- No related recipes are available, so simply invite the user to ask for something else.")
        } else {
            appendLine("- Offer the recipes under SUGGESTIONS as alternatives, naming them, and invite the user to pick one.")
            appendLine("- Never name or describe any dish that is not listed under SUGGESTIONS.")
        }
        appendLine(answerLanguageRule(language))
        if (contexts.isNotEmpty()) {
            appendLine()
            append("SUGGESTIONS:\n")
            append(suggestionBlock(contexts))
        }
    }

    private fun answerLanguageRule(language: Language): String =
        "- Write your entire answer in ${language.instructionName}. The context is in English; " +
            "translate it as needed, but keep proper nouns recognizable."

    /** Grounded context: full chunk text, each tagged with its title and category. */
    private fun contextBlock(contexts: List<RetrievalResult>): String {
        if (contexts.isEmpty()) return "(no context available)"
        return contexts.joinToString("\n\n") { r ->
            "[${r.chunk.title} — ${r.chunk.category}]\n${r.chunk.text}"
        }
    }

    /** Refusal suggestions: just the titles/categories the model may offer. */
    private fun suggestionBlock(contexts: List<RetrievalResult>): String =
        contexts.joinToString("\n") { r -> "- ${r.chunk.title} (${r.chunk.category})" }

    // ---- History budgeting --------------------------------------------------

    /**
     * Keeps the most recent history messages that fit in [budget] (newest kept first,
     * then restored to chronological order). The latest message is always included even
     * if it alone exceeds the budget — a turn with no user message is useless.
     */
    private fun fitHistory(history: List<Message>, budget: Int): List<Message> {
        val kept = ArrayDeque<Message>()
        var used = 0
        for (message in history.asReversed()) {
            val cost = estimateTokens(message.content)
            if (kept.isNotEmpty() && used + cost > budget) break
            kept.addFirst(message)
            used += cost
        }
        return kept.toList()
    }

    private fun estimateTokens(text: String): Int = (text.length + CHARS_PER_TOKEN - 1) / CHARS_PER_TOKEN

    private companion object {
        /** Coarse ~4 chars/token rule of thumb, matching the controller's max-context guard. */
        const val CHARS_PER_TOKEN = 4

        val PERSONA =
            "You are a seasoned cook in the world of The Witcher, on Sapkowski's Continent. " +
                "You speak with warmth and a little grim humor, but you are practical at the stove."
    }
}

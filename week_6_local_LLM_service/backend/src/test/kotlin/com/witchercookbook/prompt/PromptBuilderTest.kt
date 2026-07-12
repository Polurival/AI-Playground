package com.witchercookbook.prompt

import com.witchercookbook.model.Chunk
import com.witchercookbook.model.Message
import com.witchercookbook.model.RetrievalResult
import com.witchercookbook.model.Role
import com.witchercookbook.util.Language
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class PromptBuilderTest {

    private val builder = PromptBuilder(promptTokenBudget = 4096)

    private fun result(title: String, category: String, text: String, score: Double) =
        RetrievalResult(Chunk(id = title.lowercase(), title = title, category = category, text = text), score)

    private fun user(content: String) = Message(Role.USER, content)

    private fun system(messages: List<Message>) = messages.first().also { assertEquals(Role.SYSTEM, it.role) }.content

    @Test
    fun `first message is always the system prompt`() {
        val messages = builder.build(
            PromptMode.GROUNDED,
            history = listOf(user("a hearty stew")),
            contexts = listOf(result("Venison Stew", "meals", "Braise venison with root vegetables.", 0.8)),
            language = Language.ENGLISH,
        )
        assertEquals(Role.SYSTEM, messages.first().role)
        assertEquals(Role.USER, messages.last().role)
    }

    @Test
    fun `grounded prompt injects chunk text and grounding rule`() {
        val sys = system(
            builder.build(
                PromptMode.GROUNDED,
                history = listOf(user("a hearty stew")),
                contexts = listOf(result("Venison Stew", "meals", "Braise venison with root vegetables.", 0.8)),
                language = Language.ENGLISH,
            )
        )
        assertTrue(sys.contains("CONTEXT:"))
        assertTrue(sys.contains("Venison Stew"))
        assertTrue(sys.contains("Braise venison with root vegetables."))
        assertTrue(sys.contains("Use ONLY the recipes and facts in the CONTEXT"))
        assertTrue(sys.contains("answer in English"))
    }

    @Test
    fun `refusal prompt forbids invention and lists suggestions by title only`() {
        val sys = system(
            builder.build(
                PromptMode.REFUSAL,
                history = listOf(user("sushi with dragon roll pizza")),
                contexts = listOf(
                    result("Venison Stew", "meals", "Braise venison with root vegetables.", 0.2),
                    result("Redanian Goulash", "meals", "Simmer beef in paprika.", 0.18),
                ),
                language = Language.ENGLISH,
            )
        )
        assertTrue(sys.contains("NOT in this cookbook"))
        assertTrue(sys.contains("Do NOT invent"))
        assertTrue(sys.contains("SUGGESTIONS:"))
        assertTrue(sys.contains("- Venison Stew (meals)"))
        assertTrue(sys.contains("- Redanian Goulash (meals)"))
        // Refusal must not leak the full recipe body — only titles are offered.
        assertTrue(!sys.contains("Braise venison with root vegetables."))
    }

    @Test
    fun `refusal with no suggestions omits the suggestions block`() {
        val sys = system(
            builder.build(
                PromptMode.REFUSAL,
                history = listOf(user("moon cheese soufflé")),
                contexts = emptyList(),
                language = Language.ENGLISH,
            )
        )
        assertTrue(!sys.contains("SUGGESTIONS:"))
        assertTrue(sys.contains("No related recipes are available"))
    }

    @Test
    fun `answer-language instruction reflects the detected language`() {
        val ru = system(
            builder.build(
                PromptMode.GROUNDED,
                history = listOf(user("сытный зимний ужин")),
                contexts = listOf(result("Venison Stew", "meals", "Braise venison.", 0.8)),
                language = Language.RUSSIAN,
            )
        )
        assertTrue(ru.contains("answer in Russian"))
    }

    @Test
    fun `history is preserved in chronological order`() {
        val messages = builder.build(
            PromptMode.GROUNDED,
            history = listOf(user("first"), Message(Role.ASSISTANT, "a recipe"), user("second")),
            contexts = listOf(result("Stew", "meals", "text", 0.8)),
            language = Language.ENGLISH,
        )
        val history = messages.drop(1)
        assertEquals(listOf("first", "a recipe", "second"), history.map { it.content })
    }

    @Test
    fun `oldest history is trimmed to respect the token budget`() {
        // Tiny budget: only the newest turn should survive after the system prompt.
        val tight = PromptBuilder(promptTokenBudget = 1)
        val messages = tight.build(
            PromptMode.GROUNDED,
            history = listOf(user("an old long message ".repeat(5)), user("newest")),
            contexts = emptyList(),
            language = Language.ENGLISH,
        )
        val history = messages.drop(1)
        assertEquals(listOf("newest"), history.map { it.content })
    }

    @Test
    fun `latest message is kept even if it alone exceeds the budget`() {
        val tight = PromptBuilder(promptTokenBudget = 1)
        val big = "way too long ".repeat(50)
        val messages = tight.build(
            PromptMode.GROUNDED,
            history = listOf(user(big)),
            contexts = emptyList(),
            language = Language.ENGLISH,
        )
        assertEquals(big, messages.last().content)
    }

    @Test
    fun `empty history is rejected`() {
        assertFailsWith<IllegalArgumentException> {
            builder.build(PromptMode.GROUNDED, emptyList(), emptyList(), Language.ENGLISH)
        }
    }
}

package com.witchercookbook.rag

/**
 * A parsed Markdown document: frontmatter metadata plus the body below it.
 */
data class ParsedDoc(
    val title: String,
    val category: String,
    val body: String,
)

/**
 * Parses knowledge-base Markdown files that carry a minimal YAML frontmatter block.
 *
 * Expected shape (spec §11):
 * ```
 * ---
 * title: Some Title
 * category: meals
 * ---
 *
 * Body text...
 * ```
 *
 * Pure and deterministic: no I/O, no Ollama. The offline indexer (C5) reads files and hands
 * their raw contents here. Only the keys the pipeline needs (`title`, `category`) are
 * required; any other frontmatter keys are ignored.
 */
object MarkdownParser {

    private const val FENCE = "---"

    /**
     * @param raw full file contents.
     * @return the parsed title, category and trimmed body.
     * @throws IllegalArgumentException if the frontmatter block or a required key is missing.
     */
    fun parse(raw: String): ParsedDoc {
        val lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        require(lines.firstOrNull()?.trim() == FENCE) {
            "Missing frontmatter: file must start with a '---' fence"
        }

        val closingIdx = (1 until lines.size).firstOrNull { lines[it].trim() == FENCE }
            ?: throw IllegalArgumentException("Unterminated frontmatter: no closing '---' fence")

        val meta = HashMap<String, String>()
        for (i in 1 until closingIdx) {
            val line = lines[i]
            if (line.isBlank()) continue
            val sep = line.indexOf(':')
            require(sep > 0) { "Malformed frontmatter line: '$line'" }
            val key = line.substring(0, sep).trim().lowercase()
            val value = line.substring(sep + 1).trim().trim('"', '\'')
            meta[key] = value
        }

        val title = meta["title"]?.takeIf { it.isNotBlank() }
            ?: throw IllegalArgumentException("Frontmatter missing required 'title'")
        val category = meta["category"]?.takeIf { it.isNotBlank() }
            ?: throw IllegalArgumentException("Frontmatter missing required 'category'")

        val body = lines.subList(closingIdx + 1, lines.size).joinToString("\n").trim()
        return ParsedDoc(title = title, category = category, body = body)
    }
}

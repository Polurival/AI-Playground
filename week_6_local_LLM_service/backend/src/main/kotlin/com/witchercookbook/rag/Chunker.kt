package com.witchercookbook.rag

import com.witchercookbook.model.Chunk

/**
 * Cheap, tokenizer-free token estimate (~4 characters per token).
 *
 * Deterministic and dependency-free so chunk boundaries are stable and unit-testable
 * without loading a real tokenizer or contacting Ollama.
 */
fun estimateTokensByChars(text: String): Int {
    val n = text.trim().length
    return if (n == 0) 0 else (n + 3) / 4
}

/**
 * Splits a parsed document into overlapping, heading-aware chunks sized for embedding.
 *
 * Deterministic and Ollama-free (spec RAG principles): the offline indexer calls this to
 * turn each KB doc into retrieval units. Sizing uses [estimateTokens] (default ~4 chars/token)
 * so behaviour is stable and testable.
 *
 * Strategy:
 *  1. Split the body into sections at ATX headings (`#`..`######`); a chunk never spans a
 *     heading, so each chunk stays on a single topic. Overlap does not cross sections.
 *  2. Within a section, greedily pack blank-line-separated paragraphs up to [targetTokens].
 *  3. A paragraph larger than [maxTokens] is first split on sentence boundaries.
 *  4. Consecutive chunks share a small tail overlap (~[overlapTokens]) so context that
 *     straddles a boundary is retrievable from either side.
 *
 * A chunk may exceed [maxTokens] only when a single indivisible unit (one long sentence) or
 * the seeded overlap does — both unavoidable without destroying sentence integrity.
 */
class Chunker(
    private val targetTokens: Int = 300,
    private val maxTokens: Int = 400,
    private val overlapTokens: Int = 40,
    private val estimateTokens: (String) -> Int = ::estimateTokensByChars,
) {
    init {
        require(targetTokens in 1..maxTokens) { "targetTokens must be in 1..maxTokens" }
        require(overlapTokens in 0 until targetTokens) { "overlapTokens must be in 0 until targetTokens" }
    }

    private val headingRegex = Regex("^#{1,6}\\s+")
    private val paragraphSplit = Regex("\\n\\s*\\n")
    private val sentenceSplit = Regex("(?<=[.!?])\\s+")

    /**
     * @param doc parsed document (frontmatter + body).
     * @param docId stable per-document id supplied by the caller (e.g. the KB-relative path
     *   without extension). Chunk ids are "$docId#$index", 0-based.
     * @return chunks in document order; empty if the body is blank.
     */
    fun chunk(doc: ParsedDoc, docId: String): List<Chunk> {
        val texts = splitIntoSections(doc.body).flatMap { section ->
            packUnits(splitIntoUnits(section))
        }
        return texts.mapIndexed { i, text ->
            Chunk(id = "$docId#$i", title = doc.title, category = doc.category, text = text)
        }
    }

    /** Splits the body at ATX headings; each heading starts a new section it belongs to. */
    private fun splitIntoSections(body: String): List<String> {
        val sections = mutableListOf<String>()
        val current = StringBuilder()
        for (line in body.split("\n")) {
            if (headingRegex.containsMatchIn(line.trimStart()) && current.isNotBlank()) {
                sections += current.toString()
                current.setLength(0)
            }
            if (current.isNotEmpty()) current.append("\n")
            current.append(line)
        }
        if (current.isNotBlank()) sections += current.toString()
        return sections.map { it.trim() }.filter { it.isNotEmpty() }
    }

    /**
     * Turns a section into indivisible packing units: paragraphs, with any paragraph over
     * [maxTokens] broken into sentence-grouped sub-units that each fit the cap where possible.
     */
    private fun splitIntoUnits(section: String): List<String> {
        val units = mutableListOf<String>()
        for (paragraph in section.split(paragraphSplit).map { it.trim() }.filter { it.isNotEmpty() }) {
            if (estimateTokens(paragraph) <= maxTokens) {
                units += paragraph
            } else {
                units += groupSentences(paragraph)
            }
        }
        return units
    }

    /** Greedily groups sentences so each group is at most [maxTokens] (single huge sentences pass through). */
    private fun groupSentences(paragraph: String): List<String> {
        val groups = mutableListOf<String>()
        val current = StringBuilder()
        for (sentence in paragraph.split(sentenceSplit).map { it.trim() }.filter { it.isNotEmpty() }) {
            val candidate = if (current.isEmpty()) sentence else "$current $sentence"
            if (current.isNotEmpty() && estimateTokens(candidate) > maxTokens) {
                groups += current.toString()
                current.setLength(0)
                current.append(sentence)
            } else {
                current.setLength(0)
                current.append(candidate)
            }
        }
        if (current.isNotBlank()) groups += current.toString()
        return groups
    }

    /** Packs units up to [targetTokens] per chunk, seeding each new chunk with the prior tail overlap. */
    private fun packUnits(units: List<String>): List<String> {
        if (units.isEmpty()) return emptyList()

        val chunks = mutableListOf<String>()
        var current = mutableListOf<String>()
        var currentTokens = 0

        for (unit in units) {
            val unitTokens = estimateTokens(unit)
            if (current.isNotEmpty() && currentTokens + unitTokens > targetTokens) {
                val closed = current.joinToString("\n\n")
                chunks += closed
                current = overlapTail(closed)
                currentTokens = current.sumOf { estimateTokens(it) }
            }
            current += unit
            currentTokens += unitTokens
        }
        if (current.isNotEmpty()) chunks += current.joinToString("\n\n")
        return chunks
    }

    /** The trailing sentences of a closed chunk totalling ~[overlapTokens], as a single seed unit. */
    private fun overlapTail(chunkText: String): MutableList<String> {
        if (overlapTokens == 0) return mutableListOf()
        val sentences = chunkText.split(sentenceSplit).map { it.trim() }.filter { it.isNotEmpty() }
        val tail = mutableListOf<String>()
        var tokens = 0
        for (sentence in sentences.asReversed()) {
            if (tokens >= overlapTokens) break
            tail += sentence
            tokens += estimateTokens(sentence)
        }
        if (tail.isEmpty()) return mutableListOf()
        return mutableListOf(tail.asReversed().joinToString(" "))
    }
}

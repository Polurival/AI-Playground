package com.witchercookbook.model

/**
 * A retrievable unit of the knowledge base.
 *
 * Produced offline by the chunker (one Markdown doc → one or more chunks) and later
 * embedded and written to the binary index. Pure domain type: no serialization and no
 * embedding vector yet — the vector is attached downstream as an EmbeddedChunk (C4).
 *
 * @property id stable identifier, unique across the index (e.g. "meals/redanian-goulash#0").
 * @property title source document title (from frontmatter).
 * @property category source document category (from frontmatter).
 * @property text the chunk body handed to the embedder and, at query time, the prompt builder.
 */
data class Chunk(
    val id: String,
    val title: String,
    val category: String,
    val text: String,
)

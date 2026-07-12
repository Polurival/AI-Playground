package com.witchercookbook.indexer

import com.witchercookbook.config.AppConfig
import com.witchercookbook.llm.OllamaClient
import com.witchercookbook.llm.OllamaEmbedder
import com.witchercookbook.model.EmbeddedChunk
import com.witchercookbook.rag.Chunker
import com.witchercookbook.rag.IndexCodec
import com.witchercookbook.rag.MarkdownParser
import kotlinx.coroutines.runBlocking
import java.io.File

/**
 * Offline indexer: Markdown KB → chunks → embeddings → binary index (spec §11, FR-6).
 *
 * A standalone `main`, **never** invoked by the running server (R-7). It is the only
 * place embeddings are generated; the server merely loads the produced `index.bin`.
 *
 * Run with a live Ollama holding the embedding model:
 * ```
 * ./gradlew indexer                       # knowledge-base/ → index/index.bin
 * ./gradlew indexer -Pkb=path -Pindex=out.bin
 * ```
 *
 * Pipeline: [MarkdownParser] (strip frontmatter) → [Chunker] (heading-aware chunks) →
 * [OllamaEmbedder] (nomic-embed-text) → [IndexCodec] (binary write).
 */
fun main(args: Array<String>) = runBlocking {
    val config = AppConfig.load()
    val kbDir = File(args.getOrNull(0) ?: "knowledge-base")
    val outFile = File(args.getOrNull(1) ?: config.indexPath)

    require(kbDir.isDirectory) { "Knowledge base directory not found: ${kbDir.absolutePath}" }

    val files = kbDir.walkTopDown()
        .filter { it.isFile && it.extension == "md" }
        .sortedBy { it.invariantSeparatorsPath } // deterministic order
        .toList()
    require(files.isNotEmpty()) { "No .md files under ${kbDir.absolutePath}" }

    println("→ KB: ${kbDir.absolutePath}  (${files.size} files)")
    println("→ Ollama: ${config.ollamaUrl}  embed model: ${config.embedModel}")

    val chunker = Chunker()
    val chunks = files.flatMap { file ->
        val docId = file.relativeTo(kbDir).invariantSeparatorsPath.removeSuffix(".md")
        val doc = MarkdownParser.parse(file.readText())
        chunker.chunk(doc, docId)
    }
    require(chunks.isNotEmpty()) { "Chunking produced no chunks; check KB contents" }
    println("→ Chunks: ${chunks.size}")

    val embedded = OllamaClient(config).use { client ->
        val embedder = OllamaEmbedder(client)
        chunks.mapIndexed { i, chunk ->
            val vector = embedder.embed(chunk.text)
            if ((i + 1) % 10 == 0 || i == chunks.lastIndex) {
                println("  embedded ${i + 1}/${chunks.size}")
            }
            EmbeddedChunk(chunk, vector)
        }
    }

    val dim = embedded.first().vector.size
    require(embedded.all { it.vector.size == dim }) { "Inconsistent embedding dimensions" }

    IndexCodec.write(outFile, dim, embedded)
    println("✓ Wrote ${outFile.absolutePath}  (${embedded.size} chunks, dim $dim)")
}

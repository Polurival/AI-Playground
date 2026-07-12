package com.witchercookbook.rag

import com.witchercookbook.model.Chunk
import com.witchercookbook.model.EmbeddedChunk
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.File
import java.io.InputStream
import java.io.OutputStream

/**
 * Custom, self-describing binary serialization for the vector index (spec §11).
 *
 * A single file holds every chunk's metadata alongside its embedding vector so the
 * server needs only this one artifact at runtime. Symmetric [write]/[read] with a
 * magic + version + dim header that is validated on load, so an index built by a
 * mismatched indexer fails fast rather than reading garbage (R-5).
 *
 * All multi-byte numbers are big-endian (Java's [DataOutputStream] default).
 *
 * Layout:
 * ```
 * [magic "WCKB"]        4 bytes ASCII
 * [version u16]
 * [dim u16]             embedding dimension (nomic-embed-text = 768)
 * [count u32]           number of chunks
 * repeat count times:
 *   [idLen u16][id utf8]
 *   [titleLen u16][title utf8]
 *   [categoryLen u16][category utf8]
 *   [textLen u32][text utf8]
 *   [vector: dim × float32]
 * ```
 *
 * Vectors are written exactly as supplied; L2-normalizing them at build time (so
 * online search is a dot product) is the caller's choice, not encoded in the format.
 */
object IndexCodec {

    /** File magic: ASCII "WCKB". */
    private val MAGIC = "WCKB".toByteArray(Charsets.US_ASCII)

    /** Current format version. Bump on any incompatible layout change. */
    const val VERSION = 1

    private const val MAX_U16 = 0xFFFF

    // ---- Writing ------------------------------------------------------------

    /** Writes the index to [file], truncating any existing content. */
    fun write(file: File, dim: Int, chunks: List<EmbeddedChunk>) {
        file.parentFile?.mkdirs()
        file.outputStream().use { write(it, dim, chunks) }
    }

    /**
     * Serializes [chunks] (each carrying a [dim]-length vector) to [out].
     *
     * @throws IllegalArgumentException if [dim] is out of the u16 range, or any chunk's
     *   vector length differs from [dim] (a build-time programmer error).
     */
    fun write(out: OutputStream, dim: Int, chunks: List<EmbeddedChunk>) {
        require(dim in 1..MAX_U16) { "dim must be in 1..$MAX_U16, was $dim" }

        val data = DataOutputStream(out.buffered())
        data.write(MAGIC)
        data.writeShort(VERSION)
        data.writeShort(dim)
        data.writeInt(chunks.size)

        for (ec in chunks) {
            require(ec.vector.size == dim) {
                "vector dim mismatch for id '${ec.chunk.id}': expected $dim, got ${ec.vector.size}"
            }
            writeString16(data, "id", ec.chunk.id)
            writeString16(data, "title", ec.chunk.title)
            writeString16(data, "category", ec.chunk.category)
            writeString32(data, ec.chunk.text)
            for (f in ec.vector) data.writeFloat(f)
        }
        data.flush()
    }

    // ---- Reading ------------------------------------------------------------

    /** Reads the index from [file]. */
    fun read(file: File): List<EmbeddedChunk> = file.inputStream().use { read(it) }

    /**
     * Deserializes an index from [input], validating the header.
     *
     * @throws IndexFormatException if the magic, version, or dim is wrong, a declared
     *   length is negative, or the stream is truncated.
     */
    fun read(input: InputStream): List<EmbeddedChunk> {
        val data = DataInputStream(input.buffered())
        try {
            val magic = ByteArray(MAGIC.size)
            data.readFully(magic)
            if (!magic.contentEquals(MAGIC)) {
                throw IndexFormatException("not a WCKB index (bad magic header)")
            }

            val version = data.readUnsignedShort()
            if (version != VERSION) {
                throw IndexFormatException("unsupported index version $version (expected $VERSION)")
            }

            val dim = data.readUnsignedShort()
            if (dim < 1) throw IndexFormatException("invalid embedding dim $dim")

            val count = data.readInt()
            if (count < 0) throw IndexFormatException("invalid chunk count $count")

            val chunks = ArrayList<EmbeddedChunk>(count)
            repeat(count) {
                val id = readString16(data)
                val title = readString16(data)
                val category = readString16(data)
                val text = readString32(data)
                val vector = FloatArray(dim)
                for (i in 0 until dim) vector[i] = data.readFloat()
                chunks += EmbeddedChunk(Chunk(id, title, category, text), vector)
            }
            return chunks
        } catch (e: EOFException) {
            throw IndexFormatException("truncated index: unexpected end of file", e)
        }
    }

    // ---- Helpers ------------------------------------------------------------

    private fun writeString16(out: DataOutputStream, field: String, value: String) {
        val bytes = value.toByteArray(Charsets.UTF_8)
        require(bytes.size <= MAX_U16) { "$field too long for u16 length: ${bytes.size} bytes" }
        out.writeShort(bytes.size)
        out.write(bytes)
    }

    private fun writeString32(out: DataOutputStream, value: String) {
        val bytes = value.toByteArray(Charsets.UTF_8)
        out.writeInt(bytes.size)
        out.write(bytes)
    }

    private fun readString16(input: DataInputStream): String {
        val len = input.readUnsignedShort()
        return readUtf8(input, len)
    }

    private fun readString32(input: DataInputStream): String {
        val len = input.readInt()
        if (len < 0) throw IndexFormatException("invalid string length $len")
        return readUtf8(input, len)
    }

    private fun readUtf8(input: DataInputStream, len: Int): String {
        val bytes = ByteArray(len)
        input.readFully(bytes)
        return String(bytes, Charsets.UTF_8)
    }
}

/** Raised when an index file is corrupt, truncated, or built for an incompatible format. */
class IndexFormatException(message: String, cause: Throwable? = null) : RuntimeException(message, cause)

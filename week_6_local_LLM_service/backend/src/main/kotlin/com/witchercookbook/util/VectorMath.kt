package com.witchercookbook.util

import kotlin.math.sqrt

/**
 * Small, dependency-free vector helpers for cosine retrieval (spec NFR-5, NFR-7).
 *
 * Pure functions over [FloatArray]; no Ollama, no HTTP. Accumulation is done in
 * [Double] so many small float products don't lose precision.
 */
object VectorMath {

    /** Dot product of two equal-length vectors. */
    fun dot(a: FloatArray, b: FloatArray): Double {
        require(a.size == b.size) { "vector length mismatch: ${a.size} vs ${b.size}" }
        var sum = 0.0
        for (i in a.indices) sum += a[i].toDouble() * b[i].toDouble()
        return sum
    }

    /** Euclidean (L2) norm. */
    fun l2Norm(a: FloatArray): Double = sqrt(dot(a, a))

    /**
     * Unit vector in the same direction as [a]. A zero vector is returned unchanged
     * (as a copy) since it has no direction.
     */
    fun normalized(a: FloatArray): FloatArray {
        val norm = l2Norm(a)
        if (norm == 0.0) return a.copyOf()
        return FloatArray(a.size) { (a[it] / norm).toFloat() }
    }

    /**
     * Cosine similarity in [-1, 1]. Returns 0.0 if either vector is all zeros
     * (undefined direction), avoiding NaN.
     */
    fun cosineSimilarity(a: FloatArray, b: FloatArray): Double {
        val denom = l2Norm(a) * l2Norm(b)
        return if (denom == 0.0) 0.0 else dot(a, b) / denom
    }
}

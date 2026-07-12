package com.witchercookbook.util

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class VectorMathTest {

    private val eps = 1e-6

    @Test
    fun `dot product sums componentwise`() {
        assertEquals(32.0, VectorMath.dot(floatArrayOf(1f, 2f, 3f), floatArrayOf(4f, 5f, 6f)), eps)
    }

    @Test
    fun `dot rejects mismatched lengths`() {
        assertFailsWith<IllegalArgumentException> {
            VectorMath.dot(floatArrayOf(1f, 2f), floatArrayOf(1f))
        }
    }

    @Test
    fun `l2 norm is euclidean length`() {
        assertEquals(5.0, VectorMath.l2Norm(floatArrayOf(3f, 4f)), eps)
    }

    @Test
    fun `normalized yields a unit vector`() {
        val u = VectorMath.normalized(floatArrayOf(3f, 4f))
        assertEquals(1.0, VectorMath.l2Norm(u), eps)
        assertEquals(0.6, u[0].toDouble(), eps)
        assertEquals(0.8, u[1].toDouble(), eps)
    }

    @Test
    fun `normalized leaves a zero vector unchanged`() {
        val z = VectorMath.normalized(floatArrayOf(0f, 0f, 0f))
        assertTrue(z.all { it == 0f })
    }

    @Test
    fun `cosine of identical direction is 1`() {
        assertEquals(1.0, VectorMath.cosineSimilarity(floatArrayOf(1f, 2f, 3f), floatArrayOf(2f, 4f, 6f)), eps)
    }

    @Test
    fun `cosine of orthogonal vectors is 0`() {
        assertEquals(0.0, VectorMath.cosineSimilarity(floatArrayOf(1f, 0f), floatArrayOf(0f, 1f)), eps)
    }

    @Test
    fun `cosine of opposite vectors is -1`() {
        assertEquals(-1.0, VectorMath.cosineSimilarity(floatArrayOf(1f, 1f), floatArrayOf(-1f, -1f)), eps)
    }

    @Test
    fun `cosine with a zero vector is 0 not NaN`() {
        assertEquals(0.0, VectorMath.cosineSimilarity(floatArrayOf(0f, 0f), floatArrayOf(1f, 2f)), eps)
    }
}

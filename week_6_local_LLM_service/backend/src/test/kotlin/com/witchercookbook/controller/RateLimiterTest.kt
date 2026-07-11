package com.witchercookbook.controller

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class RateLimiterTest {

    /** Mutable fake clock so the token bucket is fully deterministic. */
    private class FakeClock(var nowMs: Long = 0L) : () -> Long {
        override fun invoke(): Long = nowMs
    }

    @Test
    fun `allows up to capacity then limits`() {
        val clock = FakeClock()
        val limiter = RateLimiter(capacity = 3, refillPerMinute = 60, nowMs = clock)

        repeat(3) { assertIs<RateLimiter.Decision.Allowed>(limiter.check("ip")) }
        assertIs<RateLimiter.Decision.Limited>(limiter.check("ip"))
    }

    @Test
    fun `refills over time and reports retry-after`() {
        val clock = FakeClock()
        // 60/min => 1 token/second.
        val limiter = RateLimiter(capacity = 1, refillPerMinute = 60, nowMs = clock)

        assertIs<RateLimiter.Decision.Allowed>(limiter.check("ip"))

        val limited = limiter.check("ip")
        assertIs<RateLimiter.Decision.Limited>(limited)
        assertEquals(1L, limited.retryAfterSeconds)

        // After one second a token has regenerated.
        clock.nowMs = 1_000
        assertIs<RateLimiter.Decision.Allowed>(limiter.check("ip"))
    }

    @Test
    fun `keys are isolated per client`() {
        val clock = FakeClock()
        val limiter = RateLimiter(capacity = 1, refillPerMinute = 60, nowMs = clock)

        assertIs<RateLimiter.Decision.Allowed>(limiter.check("a"))
        assertIs<RateLimiter.Decision.Limited>(limiter.check("a"))
        // A different IP has its own full bucket.
        assertIs<RateLimiter.Decision.Allowed>(limiter.check("b"))
    }

    @Test
    fun `concurrent requests never over-spend the bucket`() {
        val clock = FakeClock()
        val capacity = 100
        val limiter = RateLimiter(capacity = capacity, refillPerMinute = 1, nowMs = clock)

        val allowed = java.util.concurrent.atomic.AtomicInteger(0)
        val threads = (1..8).map {
            Thread {
                repeat(50) {
                    if (limiter.check("ip") is RateLimiter.Decision.Allowed) allowed.incrementAndGet()
                }
            }
        }
        threads.forEach { it.start() }
        threads.forEach { it.join() }

        // Refill is effectively frozen (clock never advances), so exactly the
        // initial capacity may be granted — no more, despite 400 racing attempts.
        assertEquals(capacity, allowed.get())
    }

    @Test
    fun `retry-after is at least one second`() {
        val clock = FakeClock()
        val limiter = RateLimiter(capacity = 1, refillPerMinute = 6000, nowMs = clock)
        assertIs<RateLimiter.Decision.Allowed>(limiter.check("ip"))
        val limited = limiter.check("ip")
        assertIs<RateLimiter.Decision.Limited>(limited)
        assertTrue(limited.retryAfterSeconds >= 1)
    }
}

package com.witchercookbook.controller

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.ceil

/**
 * Per-key token-bucket rate limiter, safe for concurrent access under coroutines.
 *
 * Each key (a client IP) owns an independent bucket that starts full at
 * [capacity] and refills at [refillPerMinute] tokens/minute. Each accepted
 * request costs one token; when the bucket is empty the caller is told how long
 * to wait before a token is available again.
 *
 * The limiter holds no Ktor/HTTP types — the controller layer maps [Decision]
 * onto `429` + `Retry-After`. [nowMs] is injectable so tests need no real clock.
 */
class RateLimiter(
    private val capacity: Int,
    refillPerMinute: Int,
    private val nowMs: () -> Long = System::currentTimeMillis,
) {
    init {
        require(capacity > 0) { "capacity must be > 0, was $capacity" }
        require(refillPerMinute > 0) { "refillPerMinute must be > 0, was $refillPerMinute" }
    }

    /** Milliseconds it takes to regenerate a single token. */
    private val msPerToken: Double = 60_000.0 / refillPerMinute

    private val buckets = ConcurrentHashMap<String, Bucket>()

    sealed interface Decision {
        /** Request may proceed; a token was consumed. */
        object Allowed : Decision

        /** Request rejected; retry after [retryAfterSeconds] (>= 1). */
        data class Limited(val retryAfterSeconds: Long) : Decision
    }

    /**
     * Consumes one token for [key] if available. Thread-safe: the per-key bucket
     * is mutated under its own monitor, so concurrent requests for the same IP
     * cannot over-spend the bucket.
     */
    fun check(key: String): Decision {
        val bucket = buckets.computeIfAbsent(key) { Bucket(capacity.toDouble(), nowMs()) }
        synchronized(bucket) {
            val now = nowMs()
            bucket.refill(now)
            return if (bucket.tokens >= 1.0) {
                bucket.tokens -= 1.0
                Decision.Allowed
            } else {
                val waitMs = (1.0 - bucket.tokens) * msPerToken
                Decision.Limited(ceil(waitMs / 1000.0).toLong().coerceAtLeast(1))
            }
        }
    }

    private inner class Bucket(var tokens: Double, var lastRefillMs: Long) {
        fun refill(now: Long) {
            val elapsed = now - lastRefillMs
            if (elapsed <= 0) return
            tokens = (tokens + elapsed / msPerToken).coerceAtMost(capacity.toDouble())
            lastRefillMs = now
        }
    }
}

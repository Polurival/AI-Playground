package com.witchercookbook.llm

import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.util.concurrent.atomic.AtomicInteger

/**
 * Bounds concurrent pressure on the LLM.
 *
 * A local model serves few requests at once, so unbounded concurrency just piles
 * work onto one process. This gate caps simultaneously *running* calls at
 * [maxConcurrent]. Up to [maxQueue] further callers may suspend waiting for a
 * permit; anyone arriving beyond that is rejected immediately with
 * [LlmBusyException] instead of queueing without limit.
 *
 * Admission control is a single atomic counter, so it is correct under many
 * racing coroutines: at most `maxConcurrent + maxQueue` callers are ever admitted.
 */
class LlmConcurrencyGate(
    private val maxConcurrent: Int,
    private val maxQueue: Int,
) {
    init {
        require(maxConcurrent >= 1) { "maxConcurrent must be >= 1, was $maxConcurrent" }
        require(maxQueue >= 0) { "maxQueue must be >= 0, was $maxQueue" }
    }

    private val semaphore = Semaphore(maxConcurrent)

    /** Callers currently running or waiting for a permit. */
    private val inFlight = AtomicInteger(0)

    /** Hard ceiling on admitted callers: running + queued. */
    private val limit = maxConcurrent + maxQueue

    /**
     * Runs [block] once a permit is free, suspending while up to [maxQueue] callers
     * wait. Rejects immediately with [LlmBusyException] when running + queued would
     * exceed the ceiling — no permit is acquired and [block] never runs.
     */
    suspend fun <T> withPermit(block: suspend () -> T): T {
        // Reserve a slot before suspending on the semaphore; back out if the queue
        // is full. incrementAndGet is atomic, so concurrent callers get distinct
        // values and only `limit` of them clear the check.
        if (inFlight.incrementAndGet() > limit) {
            inFlight.decrementAndGet()
            throw LlmBusyException(
                "LLM busy: $maxConcurrent in flight and queue of $maxQueue full",
            )
        }
        try {
            return semaphore.withPermit { block() }
        } finally {
            inFlight.decrementAndGet()
        }
    }
}

/** Raised when the LLM concurrency gate is saturated (running + queue both full). */
class LlmBusyException(message: String) : RuntimeException(message)

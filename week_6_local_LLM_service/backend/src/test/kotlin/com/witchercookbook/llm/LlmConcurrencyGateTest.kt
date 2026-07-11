package com.witchercookbook.llm

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.max
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * Concurrency guard for the LLM call (Task B3). Runs entirely in-process — no Ollama.
 */
class LlmConcurrencyGateTest {

    @Test
    fun `never runs more than maxConcurrent blocks at once`() = runBlocking {
        val gate = LlmConcurrencyGate(maxConcurrent = 3, maxQueue = 100)
        val active = AtomicInteger(0)
        val peak = AtomicInteger(0)

        val jobs = (1..50).map {
            launch(Dispatchers.Default) {
                gate.withPermit {
                    val now = active.incrementAndGet()
                    peak.updateAndGet { max(it, now) }
                    delay(5)
                    active.decrementAndGet()
                }
            }
        }
        jobs.joinAll()

        assertEquals(0, active.get())
        assertTrue(peak.get() <= 3, "peak concurrency ${peak.get()} exceeded 3")
    }

    @Test
    fun `all admitted callers complete`() = runBlocking {
        val gate = LlmConcurrencyGate(maxConcurrent = 4, maxQueue = 100)
        val completed = AtomicInteger(0)

        (1..40).map {
            launch(Dispatchers.Default) {
                gate.withPermit {
                    delay(2)
                    completed.incrementAndGet()
                }
            }
        }.joinAll()

        assertEquals(40, completed.get())
    }

    @Test
    fun `rejects callers once running and queue are both full`() = runBlocking {
        val gate = LlmConcurrencyGate(maxConcurrent = 1, maxQueue = 1)
        val release = CompletableDeferred<Unit>()
        val holderStarted = CompletableDeferred<Unit>()

        // Occupy the single running slot until we release it.
        val holder = launch(Dispatchers.Default) {
            gate.withPermit {
                holderStarted.complete(Unit)
                release.await()
            }
        }
        holderStarted.await()

        // Fill the one queue slot; this caller suspends waiting for the permit.
        val waiter = launch(Dispatchers.Default) {
            gate.withPermit { release.await() }
        }
        // Let the waiter reach the gate and register as in-flight.
        delay(100)

        // Running (1) + queued (1) == ceiling, so the next caller is shed.
        assertFailsWith<LlmBusyException> {
            gate.withPermit { error("must not run") }
        }

        release.complete(Unit)
        holder.join()
        waiter.join()

        // After draining, capacity is restored.
        var ran = false
        gate.withPermit { ran = true }
        assertTrue(ran)
    }

    @Test
    fun `under a burst exactly the ceiling is admitted and the rest are shed`() = runBlocking {
        val maxConcurrent = 2
        val maxQueue = 3
        val ceiling = maxConcurrent + maxQueue
        val gate = LlmConcurrencyGate(maxConcurrent, maxQueue)
        val release = CompletableDeferred<Unit>()
        val total = 30

        val running = AtomicInteger(0)   // callers inside the block right now
        val peak = AtomicInteger(0)      // most that ever ran at once
        val ranBlock = AtomicInteger(0)  // callers that ever entered the block
        val rejected = AtomicInteger(0)  // callers shed by the gate

        // Admitted blocks park on `release`, so nothing drains mid-burst: the
        // running slots stay full and the queue stays full.
        val results = (1..total).map {
            async(Dispatchers.Default) {
                try {
                    gate.withPermit {
                        ranBlock.incrementAndGet()
                        val now = running.incrementAndGet()
                        peak.updateAndGet { max(it, now) }
                        release.await()
                        running.decrementAndGet()
                    }
                } catch (e: LlmBusyException) {
                    rejected.incrementAndGet()
                }
            }
        }

        // Let admission settle. Admission is a single atomic counter, so exactly
        // `ceiling` callers pass (regardless of scheduling) and the rest are shed.
        delay(200)
        assertEquals(total - ceiling, rejected.get(), "wrong number shed")
        assertTrue(running.get() <= maxConcurrent, "running ${running.get()} exceeded $maxConcurrent")

        // Drain: the parked runners finish, and the queued callers finally enter.
        release.complete(Unit)
        results.awaitAll()

        assertEquals(ceiling, ranBlock.get(), "all admitted callers should have run the block")
        assertEquals(0, running.get())
        assertTrue(peak.get() <= maxConcurrent, "peak running ${peak.get()} exceeded $maxConcurrent")
        assertEquals(total, ranBlock.get() + rejected.get())
    }
}

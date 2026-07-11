package com.witchercookbook.config

/**
 * Typed, immutable application configuration.
 *
 * Loaded once at startup from environment variables via [load]. Every value has a
 * sane local-development default so the server runs with no environment set.
 */
data class AppConfig(
    // Server
    val serverPort: Int,

    // Ollama / models
    val ollamaUrl: String,
    val chatModel: String,
    val embedModel: String,

    // Retrieval
    val topK: Int,
    val relevanceMinScore: Double,
    val indexPath: String,

    // Rate limiting (per client IP) — consumed in Phase B2
    val rateLimitCapacity: Int,
    val rateLimitRefillPerMinute: Int,

    // Max context guards — consumed in Phase B1
    val maxContextMessages: Int,
    val maxMessageChars: Int,
    val maxContextTokens: Int,

    // LLM concurrency guard — consumed in Phase B3
    val llmMaxConcurrent: Int,
    val llmMaxQueue: Int,
) {
    companion object {
        /**
         * Reads configuration from the process environment, falling back to defaults.
         * [getenv] is injectable for testing.
         */
        fun load(getenv: (String) -> String? = System::getenv): AppConfig = AppConfig(
            serverPort = intEnv(getenv, "SERVER_PORT", 8080),
            ollamaUrl = strEnv(getenv, "OLLAMA_URL", "http://127.0.0.1:11434"),
            chatModel = strEnv(getenv, "CHAT_MODEL", "qwen3:4b"),
            embedModel = strEnv(getenv, "EMBED_MODEL", "nomic-embed-text"),
            topK = intEnv(getenv, "TOP_K", 5),
            relevanceMinScore = doubleEnv(getenv, "RELEVANCE_MIN_SCORE", 0.5),
            indexPath = strEnv(getenv, "INDEX_PATH", "index/index.bin"),
            rateLimitCapacity = intEnv(getenv, "RATE_LIMIT_CAPACITY", 10),
            rateLimitRefillPerMinute = intEnv(getenv, "RATE_LIMIT_REFILL_PER_MINUTE", 30),
            maxContextMessages = intEnv(getenv, "MAX_CONTEXT_MESSAGES", 20),
            maxMessageChars = intEnv(getenv, "MAX_MESSAGE_CHARS", 4000),
            maxContextTokens = intEnv(getenv, "MAX_CONTEXT_TOKENS", 4096),
            llmMaxConcurrent = intEnv(getenv, "LLM_MAX_CONCURRENT", 2),
            llmMaxQueue = intEnv(getenv, "LLM_MAX_QUEUE", 8),
        )

        private fun strEnv(getenv: (String) -> String?, key: String, default: String): String =
            getenv(key)?.takeIf { it.isNotBlank() } ?: default

        private fun intEnv(getenv: (String) -> String?, key: String, default: Int): Int {
            val raw = getenv(key)?.takeIf { it.isNotBlank() } ?: return default
            return raw.trim().toIntOrNull()
                ?: throw IllegalArgumentException("Invalid Int for env $key: '$raw'")
        }

        private fun doubleEnv(getenv: (String) -> String?, key: String, default: Double): Double {
            val raw = getenv(key)?.takeIf { it.isNotBlank() } ?: return default
            return raw.trim().toDoubleOrNull()
                ?: throw IllegalArgumentException("Invalid Double for env $key: '$raw'")
        }
    }
}

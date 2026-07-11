# Witcher Cookbook — Implementation Roadmap (plan.md)

> Companion to `spec.md`. This is the **how** and **in what order**. Each task is small, independently testable, leaves the project in a working state, and fits a single Claude Code session. Do one task at a time. Do not refactor unrelated code.

**How to read a task.** Every task lists: Goal · Description · Files expected to change · Dependencies · Definition of Done · Manual verification · Recommended Claude configuration (Model / Thinking / Effort + why).

**Model note.** The assignment enumerates *Opus 4.1* and *Sonnet 4* as the configuration choices, so those are used below. (If a newer model is available in your Claude Code, prefer the current-generation equivalent: Opus-class for architecture/serialization-critical work, Sonnet-class for mechanical/UI work.)

**Strategy.** Phase A builds the minimal vertical slice (React → Ktor → Ollama → chat) so the project is usable ASAP. Phase B hardens the API (concurrency, rate limit, max context). Phase C adds the custom RAG. Phase D wires RAG in + language handling. Phase E adds streaming. Phase F handles deployment. Phase G is polish.

---

## Phase A — Vertical Slice (React → Ktor → Ollama → Chat)

### Task A1 — Backend skeleton + health endpoint
- **Goal:** A running Ktor server exposing `GET /api/health`.
- **Description:** Create the Gradle project (Kotlin, Ktor, kotlinx.serialization, Coroutines). Set up `Application.kt`, base routing, JSON negotiation, package skeleton (`config`, `controller`, `service`, `rag`, `prompt`, `llm`, `model`, `util`, `indexer`). Implement `/api/health` returning a static `{ "status": "ok" }`.
- **Files expected to change:** `backend/build.gradle.kts`, `backend/settings.gradle.kts`, `backend/src/main/kotlin/com/witchercookbook/Application.kt`, `.../controller/HealthController.kt`.
- **Dependencies:** none.
- **Definition of Done:** `./gradlew run` starts; `curl localhost:8080/api/health` → `200 {"status":"ok"}`.
- **Manual verification:** Run server; curl the endpoint; confirm JSON + 200.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Project bootstrap and dependency/versioning choices set the foundation; reasoning helps avoid Gradle/Ktor setup pitfalls.

### Task A2 — Config module
- **Goal:** Typed configuration from environment variables with sane defaults.
- **Description:** Add `config/AppConfig.kt` reading `SERVER_PORT`, `OLLAMA_URL`, `CHAT_MODEL` (qwen3:4b), `EMBED_MODEL` (nomic-embed-text), `TOP_K`, `RELEVANCE_MIN_SCORE`, `RATE_LIMIT_*`, `MAX_CONTEXT_*`, `INDEX_PATH`. Immutable data class, single load point at startup.
- **Files expected to change:** `.../config/AppConfig.kt`, `Application.kt` (wire config).
- **Dependencies:** A1.
- **Definition of Done:** Config loads with defaults; overriding an env var changes behavior (e.g., port).
- **Manual verification:** Start with `SERVER_PORT=9090`; confirm it binds 9090.
- **Claude config:** **Sonnet 4 · Thinking OFF · Effort Low.** Mechanical, well-scoped.

### Task A3 — Ollama chat client (non-streaming)
- **Goal:** `OllamaClient.chat(...)` calls local Ollama and returns a complete response.
- **Description:** Implement `llm/OllamaClient.kt` (Ktor HTTP client) hitting Ollama's chat/generate API against `qwen3:4b`. Suspend function, timeouts, basic retry, typed request/response DTOs. No prompt assembly here.
- **Files expected to change:** `.../llm/OllamaClient.kt`, `.../llm/OllamaDtos.kt`, `build.gradle.kts` (client engine).
- **Dependencies:** A2; Ollama running with `qwen3:4b`.
- **Definition of Done:** A small manual harness / test calls `chat("Say hi")` and prints a real completion.
- **Manual verification:** With `ollama serve` up, run the harness; see a coherent reply.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Correct HTTP contract + coroutine/timeout handling is the backbone of the service.

### Task A4 — ChatService + `/api/chat` (no RAG yet)
- **Goal:** `POST /api/chat` returns an LLM answer end-to-end.
- **Description:** Add domain `model` types (`Message`, `ChatRequest`, `ChatResponse`), `service/ChatService.kt` (orchestration; passes messages straight to a minimal prompt for now), `controller/ChatController.kt` with request DTOs and mapping. No Ktor types below the controller.
- **Files expected to change:** `.../model/*.kt`, `.../service/ChatService.kt`, `.../controller/ChatController.kt`, `Application.kt` (routing/wiring).
- **Dependencies:** A3.
- **Definition of Done:** `curl -X POST /api/chat -d '{"messages":[{"role":"user","content":"a soup recipe"}]}'` returns a generated recipe.
- **Manual verification:** POST a message; receive a coherent recipe JSON.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Establishes the controller↔service boundary (NFR-5); worth reasoning to keep it clean.

### Task A5 — Frontend chat UI
- **Goal:** A React SPA that chats with the backend.
- **Description:** Vite + React + TypeScript app: a message list, an input box, and a call to `POST /api/chat`. Dev proxy to `:8080`. Minimal styling. Client holds full history (stateless server).
- **Files expected to change:** `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/main.tsx`.
- **Dependencies:** A4.
- **Definition of Done:** `npm run dev`; typing a request shows a generated recipe in the UI.
- **Manual verification:** Open the dev URL; send "hearty stew"; see the recipe render.
- **Claude config:** **Sonnet 4 · Thinking OFF · Effort Low.** Standard frontend scaffolding; low architectural risk.

> **Milestone A:** Usable end-to-end chat (React → Ktor → Ollama). RAG not yet involved.

---

## Phase B — API Hardening (assignment verification points)

### Task B1 — Max context limits
- **Goal:** Reject/limit oversized requests before they reach Ollama.
- **Description:** In the controller, enforce max message length, max history length, and an approximate token budget. Return `413 CONTEXT_TOO_LARGE`. Add config knobs (from A2).
- **Files expected to change:** `.../controller/ChatController.kt`, `.../controller/Validation.kt`, `.../config/AppConfig.kt`.
- **Dependencies:** A4.
- **Definition of Done:** Oversized request → `413`; normal request unaffected; Ollama not called on rejection.
- **Manual verification:** POST a huge message → 413; POST a normal one → 200.
- **Claude config:** **Sonnet 4 · Thinking ON · Effort Low.** Simple logic; a little reasoning to pick sensible token-estimation.

### Task B2 — Rate limiting
- **Goal:** Per-IP rate limiting with `429` + `Retry-After`.
- **Description:** Add a lightweight in-memory rate limiter (token-bucket/sliding-window) keyed by client IP (honoring `X-Forwarded-For` from Nginx). Configurable rate/burst. Return `429` with `Retry-After`.
- **Files expected to change:** `.../controller/RateLimiter.kt`, plugin/middleware wiring in `Application.kt`, `.../config/AppConfig.kt`.
- **Dependencies:** A4, A2.
- **Definition of Done:** Rapid requests beyond the limit → `429` with `Retry-After`.
- **Manual verification:** Loop `curl` past the limit; observe 429s and the header.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Concurrency-correct limiter (thread-safe under coroutines) deserves care.

### Task B3 — Concurrency guard + verification
- **Goal:** Correct behavior under simultaneous requests; bound pressure on Ollama.
- **Description:** Put a bounded semaphore/queue in front of the Ollama call so concurrency is capped; excess either queues or returns `503 LLM_UNAVAILABLE`. Add a concurrency test (fire N parallel `/api/chat`).
- **Files expected to change:** `.../service/ChatService.kt` (or a small `llm/Concurrency.kt`), test under `test/`.
- **Dependencies:** A4, B2.
- **Definition of Done:** N parallel requests all return valid responses (or clean 503s); no corruption; test passes.
- **Manual verification:** Run the parallel test / a shell `xargs -P` burst; confirm all succeed or degrade cleanly.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort High.** Structured concurrency correctness is subtle and central to NFR-2.

> **Milestone B:** Remote access, concurrency, rate limiting, and max-context all verifiable (AC-3..AC-6).

---

## Phase C — Custom RAG Core (offline + retrieval, no wiring yet)

### Task C1 — Author the Markdown knowledge base
- **Goal:** ~20–50 English Markdown docs across categories.
- **Description:** Hand-write KB files (locations, taverns, ingredients, drinks, meals, regions; optional monsters/herbs). Each file has frontmatter (`title`, `category`) + concise English body, per the format in `spec.md` §11.
- **Files expected to change:** `knowledge-base/**/*.md`.
- **Dependencies:** none (can run in parallel with Phase A/B).
- **Definition of Done:** 20–50 valid Markdown files with consistent frontmatter.
- **Manual verification:** Skim files; confirm frontmatter + coverage across categories.
- **Claude config:** **Sonnet 4 · Thinking OFF · Effort Medium.** Content authoring; Sonnet is efficient at drafting many small docs.

### Task C2 — Markdown parsing + chunking
- **Goal:** Deterministic chunker turning KB files into chunks with metadata.
- **Description:** `rag/Chunker.kt` + `rag/MarkdownParser.kt`: strip/read frontmatter, split heading-aware into ~200–400 token chunks with small overlap; each chunk carries `id`, `title`, `category`, `text`. Pure functions, unit-tested (no Ollama).
- **Files expected to change:** `.../rag/MarkdownParser.kt`, `.../rag/Chunker.kt`, `.../model/Chunk.kt`, tests.
- **Dependencies:** C1 (sample files for tests).
- **Definition of Done:** Given a sample doc, chunker yields expected chunk count/boundaries; tests pass without Ollama.
- **Manual verification:** Run unit tests; inspect chunk output for one file.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Chunking quality directly affects retrieval; edge cases (headings, overlap) merit reasoning.

### Task C3 — Embedding function (nomic-embed-text)
- **Goal:** `Embedder` interface + Ollama-backed implementation.
- **Description:** Add `llm/Embedder.kt` interface (`suspend fun embed(text): FloatArray`) and an Ollama implementation using `nomic-embed-text`. The interface keeps `rag` decoupled from the LLM transport (spec §6.2).
- **Files expected to change:** `.../llm/Embedder.kt`, `.../llm/OllamaEmbedder.kt`, `.../llm/OllamaClient.kt` (embeddings endpoint).
- **Dependencies:** A3.
- **Definition of Done:** `embed("venison stew")` returns a 768-dim vector.
- **Manual verification:** Harness prints vector length 768 and a few values.
- **Claude config:** **Sonnet 4 · Thinking ON · Effort Low.** Small addition mirroring the existing client; light reasoning on the API shape.

### Task C4 — Binary index format (writer + reader)
- **Goal:** Custom binary serialization for the vector index.
- **Description:** `rag/IndexCodec.kt` implementing the format in `spec.md` §11 (magic, version, dim, count, per-chunk metadata + float32 vector; optional build-time L2 normalization). Symmetric write/read with validation (magic/version/dim). Round-trip unit test.
- **Files expected to change:** `.../rag/IndexCodec.kt`, `.../model/EmbeddedChunk.kt`, tests.
- **Dependencies:** C2.
- **Definition of Done:** Write→read round-trips identical chunks/vectors; corrupt/mismatched header fails fast with a clear error.
- **Manual verification:** Run round-trip test; hex-inspect header bytes optionally.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort High.** Hand-rolled binary I/O is error-prone (endianness, lengths, versioning); correctness is critical (R-5).

### Task C5 — Offline indexer app
- **Goal:** A standalone `main` that builds `index.bin` from the KB.
- **Description:** `indexer/IndexerApp.kt`: read `knowledge-base/`, chunk (C2), embed (C3), write index (C4). Own Gradle run task (e.g., `./gradlew indexer`). **Never** runs inside the server.
- **Files expected to change:** `.../indexer/IndexerApp.kt`, `build.gradle.kts` (indexer task).
- **Dependencies:** C2, C3, C4; Ollama with `nomic-embed-text`.
- **Definition of Done:** Running the indexer produces `index/index.bin`; logs chunk count.
- **Manual verification:** Run indexer; confirm `index.bin` exists and chunk count matches expectation.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Ties the offline pipeline together; separation from the server must be enforced (R-7).

### Task C6 — Cosine similarity search
- **Goal:** In-memory top-K retrieval.
- **Description:** `rag/VectorIndex.kt` (loads via C4, holds vectors) + `rag/SimilaritySearch.kt` (cosine / dot-product on normalized vectors, top-K). No Ollama, no HTTP. Unit tests with synthetic vectors.
- **Files expected to change:** `.../rag/VectorIndex.kt`, `.../rag/SimilaritySearch.kt`, `.../util/VectorMath.kt`, tests.
- **Dependencies:** C4.
- **Definition of Done:** Given synthetic vectors, search returns the expected nearest chunks in order; tests pass without Ollama.
- **Manual verification:** Run search unit tests; verify ranking on a crafted example.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Numeric correctness (normalization, tie-handling) matters; keep it dependency-free (NFR-5).

> **Milestone C:** A real `index.bin` exists and retrieval works in isolation — still not wired into chat.

---

## Phase D — RAG Integration + Language Handling

### Task D1 — Load index at startup
- **Goal:** Server loads `index.bin` into memory on boot; health reports it.
- **Description:** Wire `VectorIndex` load at startup from `INDEX_PATH`; extend `/api/health` with `indexLoaded` + `chunks`. Fail fast if missing/invalid. Server must **not** embed the KB.
- **Files expected to change:** `Application.kt`, `.../controller/HealthController.kt`, `.../rag/VectorIndex.kt`.
- **Dependencies:** C6, C5 (an index to load).
- **Definition of Done:** Startup loads the index; `/api/health` shows `indexLoaded:true` and chunk count.
- **Manual verification:** Start server; curl health; confirm counts. Rename index → server fails fast.
- **Claude config:** **Sonnet 4 · Thinking ON · Effort Low.** Straightforward wiring; a little reasoning for fail-fast behavior.

### Task D2 — Language detection
- **Goal:** Detect the query language to set the answer language.
- **Description:** `util/LanguageDetector.kt` — lightweight heuristic (script/character-range + common-word signals) returning a language tag. No heavy dependency. Unit-tested on RU/EN/PL samples.
- **Files expected to change:** `.../util/LanguageDetector.kt`, tests.
- **Dependencies:** none.
- **Definition of Done:** Detects Russian vs English vs Polish on sample inputs; tests pass.
- **Manual verification:** Run tests with mixed-language samples.
- **Claude config:** **Sonnet 4 · Thinking ON · Effort Low.** Bounded heuristic; light reasoning on signals.

### Task D3 — PromptBuilder (grounding + refusal)
- **Goal:** Single place that assembles the grounded prompt, incl. the no-invention rule.
- **Description:** `prompt/PromptBuilder.kt` — build system prompt (Witcher persona, grounding rules, "answer in {language}"), inject top-K English chunks as context, append user history within a token budget. **Two modes** driven by the caller: (a) **grounded** — generate strictly from context; (b) **refusal-with-suggestion** — when the dish is absent (no chunk clears the relevance threshold), instruct the model to state the dish cannot be cooked from this cookbook and propose the supplied nearest recipe(s) as alternatives, never inventing a dish. **Only** component that assembles prompts. Unit-tested (pure) for both modes.
- **Files expected to change:** `.../prompt/PromptBuilder.kt`, tests.
- **Dependencies:** C6 (chunk type), D2 (language).
- **Definition of Done:** Given chunks + history + language, produces the expected prompt for both grounded and refusal modes; respects budget; tests pass.
- **Manual verification:** Snapshot-test the assembled prompt for a grounded input and for a refusal input.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort High.** Prompt design drives output quality and grounding (R-2); the central knob worth deep reasoning.

### Task D4 — Wire RAG into ChatService
- **Goal:** Chat answers are grounded and language-correct end-to-end.
- **Description:** Update `ChatService`: detect language (D2) → embed query (C3) → search (C6) → **compare top score to `RELEVANCE_MIN_SCORE`** to pick grounded vs refusal-with-suggestion mode → build prompt (D3) → call Ollama (A3). Return `sources` (title + score). Remove the A4 pass-through prompt.
- **Files expected to change:** `.../service/ChatService.kt`, `.../controller/ChatController.kt` (sources in DTO), `.../model/*`.
- **Dependencies:** D1, D2, D3, C3, C6.
- **Definition of Done:** `POST /api/chat` returns a grounded recipe + `sources`; a Russian query returns a Russian answer; a request for a dish absent from the KB returns a refusal-with-suggestion (no invented dish).
- **Manual verification:** Ask "hearty winter dinner" (EN) and "сытный зимний ужин" (RU); verify grounding + answer language + `sources`. Then ask for something clearly absent (e.g. "sushi with dragon roll pizza") → confirm refusal + a related KB suggestion, not a fabricated recipe.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort High.** The orchestration where all boundaries meet; correctness of the full data flow (spec §10) and the threshold branch is critical.

### Task D5 — Show sources in the frontend
- **Goal:** UI displays which KB chunks grounded the answer.
- **Description:** Render the `sources` list (titles + scores) beneath each assistant message.
- **Files expected to change:** `frontend/src/App.tsx`, `frontend/src/api.ts` (types).
- **Dependencies:** D4.
- **Definition of Done:** Sources render under answers in the UI.
- **Manual verification:** Send a query; see sources listed.
- **Claude config:** **Sonnet 4 · Thinking OFF · Effort Low.** Small UI addition.

> **Milestone D:** Full custom-RAG chat, grounded, multilingual answers (AC-1, AC-2, AC-7, AC-8).

---

## Phase E — Streaming

### Task E1 — Streaming Ollama chat
- **Goal:** `OllamaClient` can stream tokens.
- **Description:** Add a streaming variant returning a `Flow<String>` from Ollama's streaming response. Keep the non-streaming path intact.
- **Files expected to change:** `.../llm/OllamaClient.kt`.
- **Dependencies:** A3.
- **Definition of Done:** A harness prints tokens incrementally as they arrive.
- **Manual verification:** Run harness; observe incremental output.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Streaming parsing + Flow lifecycle/cancellation needs care.

### Task E2 — SSE endpoint + streaming UI
- **Goal:** End-to-end streaming when `stream:true`.
- **Description:** Controller emits `text/event-stream` for `stream:true`, ending with a final event carrying `sources`. Frontend consumes SSE and renders tokens live.
- **Files expected to change:** `.../controller/ChatController.kt`, `.../service/ChatService.kt`, `frontend/src/api.ts`, `frontend/src/App.tsx`.
- **Dependencies:** E1, D4.
- **Definition of Done:** UI shows tokens streaming in; final `sources` render after completion.
- **Manual verification:** Toggle streaming in the UI; watch live tokens; confirm sources at end.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort High.** SSE framing + client incremental parsing + cancellation are error-prone across the stack.

> **Milestone E:** Streaming responses end-to-end (FR-8).

---

## Phase F — Deployment (VPS)

### Task F1 — Backend packaging + systemd unit
- **Goal:** Runnable server artifact + service unit.
- **Description:** Fat-jar (or distribution) Gradle task; `deploy/witcher-backend.service` systemd unit with env vars, restart policy, `INDEX_PATH`.
- **Files expected to change:** `backend/build.gradle.kts`, `deploy/witcher-backend.service`.
- **Dependencies:** D4.
- **Definition of Done:** Jar builds and runs standalone; unit file is valid.
- **Manual verification:** Build jar; `java -jar` runs locally; `systemd-analyze verify` the unit.
- **Claude config:** **Sonnet 4 · Thinking ON · Effort Low.** Standard packaging; light reasoning on env wiring.

### Task F2 — Frontend build + Nginx (TLS) config
- **Goal:** Static SPA served by Nginx with TLS, `/api/*` proxied to Ktor.
- **Description:** `vite build` output; `deploy/nginx.conf` serving `static/` and reverse-proxying `/api/*` to `127.0.0.1:8080`, forwarding `X-Forwarded-For`; Let's Encrypt notes. Ollama stays on localhost.
- **Files expected to change:** `deploy/nginx.conf`, `deploy/README.md`.
- **Dependencies:** A5, F1.
- **Definition of Done:** Nginx config is valid (`nginx -t`); routes static + `/api` correctly in a local test.
- **Manual verification:** `nginx -t`; hit `/` (SPA) and `/api/health` through the proxy.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort Medium.** Correct proxy/TLS/`X-Forwarded-For` (feeds B2 rate limiting) matters for security (NFR-10, R-4).

### Task F3 — Deployment runbook
- **Goal:** Reproducible VPS deploy steps.
- **Description:** `deploy/README.md`: VPS prep, `ollama pull qwen3:4b nomic-embed-text`, ship `backend.jar` + `static/` + `index.bin`, enable systemd units, Let's Encrypt issuance, smoke tests. Emphasize: server never rebuilds embeddings; Ollama not public.
- **Files expected to change:** `deploy/README.md`.
- **Dependencies:** F1, F2, C5.
- **Definition of Done:** A reader can follow the runbook start-to-finish without gaps.
- **Manual verification:** Dry-run the steps mentally/locally; confirm ordering and prerequisites.
- **Claude config:** **Sonnet 4 · Thinking ON · Effort Medium.** Documentation with some sequencing judgment.

> **Milestone F:** Live on the VPS; remote HTTPS access verified (AC-3).

---

## Phase G — Polish & Verification

### Task G1 — End-to-end acceptance pass
- **Goal:** Verify all acceptance criteria (spec §15).
- **Description:** Walk AC-1..AC-11: health/index, grounded chat, remote access, concurrency, rate limit, max context, RU→RU answer, architecture boundaries (grep for forbidden imports), tests-without-Ollama.
- **Files expected to change:** possibly a `deploy/SMOKE_TESTS.md` / checklist; small fixes as found.
- **Dependencies:** all prior.
- **Definition of Done:** Every AC passes or has a tracked follow-up.
- **Manual verification:** Execute the checklist against the deployed service.
- **Claude config:** **Opus 4.1 · Thinking ON · Effort High.** Cross-cutting verification and boundary audits benefit from careful reasoning.

### Task G2 — Observability & logging
- **Goal:** Useful structured logs/metrics.
- **Description:** Log request lifecycle, retrieval scores, Ollama latency, rate-limit hits. Optional simple counters.
- **Files expected to change:** logging config, small touches in controller/service/llm.
- **Dependencies:** D4.
- **Definition of Done:** Logs show per-request retrieval + latency; rate-limit events visible.
- **Manual verification:** Send requests; inspect logs for the fields.
- **Claude config:** **Sonnet 4 · Thinking OFF · Effort Low.** Additive, low-risk.

---

## Task ↔ Acceptance Criteria Map

| AC | Covered by |
|---|---|
| AC-1 index loaded, no rebuild | C5, D1 |
| AC-2 grounded recipe + sources | D3, D4 |
| AC-3 remote HTTPS access | F2, F3 |
| AC-4 concurrency | B3 |
| AC-5 rate limit 429 | B2 |
| AC-6 max context 413 | B1 |
| AC-7 RU query → RU answer | D2, D3, D4 |
| AC-8 indexer builds index | C5 |
| AC-9 architecture boundaries | A4, C6, D3 (audited in G1) |
| AC-10 tests without Ollama | C2, C4, C6, D2, D3 |
| AC-11 vertical slice first | A1–A5 |
| AC-12 refusal-with-suggestion (no invention) | C6 (threshold), D3, D4 |

---

## Configuration Rationale (summary)

- **Opus 4.1 · Thinking ON** for foundation, concurrency, binary I/O, prompt design, RAG orchestration, and streaming — tasks where subtle correctness or architecture decisions have outsized cost if wrong.
- **Sonnet 4 · Thinking OFF/Low** for scaffolding, content authoring, small UI, and additive docs/logging — mechanical, well-bounded work where speed wins.
- **Effort High** is reserved for the highest-risk correctness tasks (concurrency B3, binary codec C4, PromptBuilder D3, RAG wiring D4, streaming E2, acceptance G1).
```

# Witcher Cookbook — Specification (spec.md)

> Specification-Driven Development document. This is the source of truth for **what** we build and **why**. Implementation must follow this file and `plan.md`. No code lives here.

---

## 1. Project Overview

**Witcher Cookbook** is a private, self-hosted AI service that generates cooking recipes inspired by *The Witcher* universe (Andrzej Sapkowski's novels and CD Projekt RED's games).

It runs **entirely locally** on a VPS. No OpenAI, no external LLM APIs. Inference is served by a local **Ollama** instance running `qwen3:4b` (generation) and `nomic-embed-text` (embeddings).

Recipes are grounded in a curated **Markdown knowledge base** (locations, taverns, ingredients, drinks, meals, regions, and optionally monsters/herbs) via a **hand-written Retrieval-Augmented Generation (RAG)** pipeline. No third-party vector database or LLM framework is used — chunking, embedding storage, and cosine similarity search are implemented from scratch.

---

## 2. Goals

- Deploy a **local LLM as a private HTTP service** on a VPS.
- Expose a clean **HTTP chat API** that generates Witcher-themed recipes.
- Ground generation in a **custom, from-scratch RAG** pipeline over a Markdown knowledge base.
- Support **remote network access**, **multiple simultaneous requests**, **rate limiting**, and **maximum context limits**.
- Ship a minimal **React + TypeScript + Vite** frontend for chatting with the service.
- Keep the codebase **readable, modular, testable, idiomatic Kotlin, coroutine-based, and easy to extend**.
- Reach a usable vertical slice (React → Ktor → Ollama → Chat) as early as possible, then layer RAG on top.
- Support **streaming responses** in the architecture from the start, even if the MVP returns complete responses.

---

## 3. Non-Goals

- No external/cloud LLM APIs (OpenAI, Anthropic, etc.).
- No LangChain, LangChain4j, ChromaDB, FAISS, Qdrant, Pinecone, or Spring Boot.
- No user accounts, login, JWT, or multi-tenant authentication (service is single-user-private; protected by rate limiting + network placement).
- No server-side conversation persistence — **chat is stateless** (the client sends the full history each request).
- No automated Markdown importer in the MVP (KB is authored by hand).
- No rebuilding of embeddings at server startup — embeddings are generated **offline only**.
- No fine-tuning or training of models.
- No mobile app.

---

## 4. Functional Requirements

- **FR-1 — Chat endpoint.** `POST /api/chat` accepts a user message (plus optional prior messages) and returns a generated recipe/answer.
- **FR-2 — RAG grounding.** The service retrieves the top-K most relevant knowledge chunks and injects them into the prompt before calling the LLM.
- **FR-3 — Stateless conversation.** The client supplies the full message history; the server stores nothing between requests.
- **FR-4 — Multilingual queries.** The user may write in any language. The knowledge base and embeddings are English. The backend detects the query language, retrieves over English embeddings, and instructs the model to **answer in the user's language**.
- **FR-5 — Health endpoint.** `GET /api/health` reports service liveness and (optionally) Ollama reachability and index-loaded status.
- **FR-6 — Offline indexer.** A standalone tool (not the server) reads the Markdown KB, chunks it, generates embeddings via Ollama, and writes a **binary vector index** to disk.
- **FR-7 — Index loading.** On startup the server loads the pre-built binary index into memory. It must **never** regenerate embeddings.
- **FR-8 — Streaming-ready.** The service architecture supports streaming token output from Ollama; MVP may return a complete response.
- **FR-9 — Frontend chat UI.** A React SPA lets the user type a request and view the generated recipe.
- **FR-10 — Grounded refusal (no invention).** If the requested dish is **not present** in the knowledge base — i.e. the top retrieval score falls below a configurable relevance threshold — the service must **not** invent a recipe. It answers that the dish cannot be cooked here and **proposes the closest related recipe(s)** actually found in the KB. Recipes are always grounded in retrieved chunks; the model must not fabricate dishes absent from the KB.

---

## 5. Non-Functional Requirements

- **NFR-1 — Remote access.** The API is reachable over the network from a remote client (verified end-to-end).
- **NFR-2 — Concurrency.** The service handles multiple simultaneous requests without corruption or blocking, using Kotlin coroutines / structured concurrency.
- **NFR-3 — Rate limiting.** Requests are rate-limited (per client IP) to protect the single local GPU/CPU-bound Ollama backend.
- **NFR-4 — Maximum context limits.** The service enforces a maximum input size (message length / total prompt tokens / history length) and rejects or truncates oversized requests with a clear error.
- **NFR-5 — Clean Architecture.** Business logic does not depend on HTTP; retrieval does not depend on Ollama; prompt assembly lives only in `PromptBuilder`.
- **NFR-6 — Testability.** Core modules (chunking, cosine search, prompt building, language detection) are unit-testable without a running Ollama or HTTP server.
- **NFR-7 — Minimal dependencies.** No heavyweight frameworks beyond Ktor + kotlinx.serialization + Kotlin Coroutines.
- **NFR-8 — Idiomatic Kotlin.** Immutable data classes, constructor injection, suspend functions, small focused classes, no global mutable state.
- **NFR-9 — Observability.** Structured logging of request lifecycle, retrieval hits, and Ollama call latency.
- **NFR-10 — Security posture.** TLS at the edge (Nginx + Let's Encrypt); Ollama bound to localhost only, never exposed publicly.

---

## 6. Architecture

Clean Architecture with clear separation of responsibilities. HTTP is an entry adapter; Ollama is an outbound adapter; the RAG core is framework-free.

### 6.1 Layered view

```
          ┌─────────────────────────────────────────────┐
   HTTP → │  controller   (Ktor routes, DTOs, validation) │
          └───────────────┬─────────────────────────────┘
                          │  (domain models, no HTTP types)
          ┌───────────────▼─────────────────────────────┐
          │  service      (ChatService — orchestration)   │
          └───┬───────────────┬───────────────┬──────────┘
              │               │               │
   ┌──────────▼───┐   ┌───────▼──────┐   ┌────▼─────────┐
   │  rag         │   │  prompt      │   │  llm         │
   │  retrieval   │   │  PromptBuilder│  │  OllamaClient │
   │  (no Ollama) │   │  (only place  │  │  (only place  │
   │              │   │   prompts are │  │   Ollama is   │
   │              │   │   assembled)  │  │   called)     │
   └──────┬───────┘   └──────────────┘   └──────┬───────┘
          │  loads                              │  HTTP
   ┌──────▼───────┐                      ┌──────▼───────┐
   │ binary index │                      │   Ollama     │
   │  (on disk)   │                      │  (localhost) │
   └──────────────┘                      └──────────────┘
```

### 6.2 Dependency rules

- `controller` depends on `service` and `model`; it may not leak Ktor types downward.
- `service` orchestrates `rag`, `prompt`, `llm`. It contains business logic and does **not** import Ktor.
- `rag` (retrieval + index) has **no dependency on Ollama or HTTP**. It consumes pre-computed embeddings and performs cosine search. The one place `rag` needs an embedding of the *query* is behind an `Embedder` interface so retrieval stays decoupled from the LLM transport.
- `prompt.PromptBuilder` is the **only** component that assembles prompt text.
- `llm.OllamaClient` is the **only** component that talks to Ollama.
- `config` provides typed configuration from environment variables.
- `indexer` is a **separate offline entry point** (own `main`), not part of the running server.

---

## 7. Deployment Architecture

Development and index generation happen **locally**. Only artifacts are shipped to the VPS.

```
Local machine (offline)                     VPS (runtime)
───────────────────────                     ─────────────────────────────
Markdown KB  ─┐                             Internet
              │  ./gradlew indexer            │  HTTPS
Indexer  ─────┼──► index.bin  ──── scp ─────► │
              │                             ┌─▼──────────────────────────┐
Backend build ┼──► backend.jar ─── scp ────►│ Nginx (TLS, Let's Encrypt) │
Frontend build┴──► static/     ─── scp ────►│   ├─ /        → static SPA  │
                                            │   └─ /api/*   → Ktor :8080  │
                                            │ Ktor backend (systemd)      │
                                            │   loads index.bin at start  │
                                            │ Ollama (systemd, 127.0.0.1) │
                                            │   qwen3:4b, nomic-embed-text │
                                            └────────────────────────────┘
```

- **Nginx** terminates TLS (Let's Encrypt), serves the static React build, and reverse-proxies `/api/*` to Ktor on `127.0.0.1:8080`.
- **Ktor** runs as a `systemd` service; loads `index.bin` on startup.
- **Ollama** runs as a `systemd` service bound to `127.0.0.1:11434`, **not** exposed publicly.
- Models (`qwen3:4b`, `nomic-embed-text`) are pulled on the VPS once via `ollama pull`.
- The server **never** rebuilds embeddings.

---

## 8. Module Responsibilities

| Module | Responsibility | Must NOT |
|---|---|---|
| `controller` | Ktor routing, request/response DTOs, input validation, rate limiting, max-context enforcement, error mapping. | Contain business logic or call Ollama directly. |
| `service` | `ChatService`: orchestrate retrieval → prompt → LLM; enforce domain rules. | Import Ktor or HTTP types. |
| `rag` | Load binary index, hold vectors in memory, cosine similarity search, top-K selection, chunk model. | Depend on Ollama or HTTP. |
| `prompt` | `PromptBuilder`: assemble system + context + user prompt; inject retrieved chunks; set answer-language instruction; enforce grounding + refusal-when-absent rules in the system prompt. | Perform retrieval or call the LLM. |
| `llm` | `OllamaClient`: chat generation (streaming-capable) and embedding generation; retries/timeouts. | Assemble prompts or know about routes. |
| `model` | Domain data classes (Message, Chunk, EmbeddedChunk, RetrievalResult, ChatRequest/Response domain forms). | Contain logic. |
| `config` | Typed config from env (ports, Ollama URL, model names, top-K, relevance threshold, rate-limit, max-context, index path). | Hardcode secrets. |
| `util` | Small cross-cutting helpers (language detection, cosine math, binary I/O helpers). | Become a dumping ground. |
| `indexer` (offline) | Read Markdown → chunk → embed (via `OllamaClient`) → write binary index. Separate `main`. | Run inside the server process. |

---

## 9. API Overview

Base path: `/api`. Content type: `application/json`. No authentication (rate-limited, TLS at edge).

### `GET /api/health`
Liveness + readiness.
```json
// 200 OK
{ "status": "ok", "ollama": "reachable", "indexLoaded": true, "chunks": 137 }
```

### `POST /api/chat`
Generate a recipe. Stateless — client sends full history.

Request:
```json
{
  "messages": [
    { "role": "user", "content": "Хочу сытный зимний ужин для ведьмака" }
  ],
  "stream": false
}
```

Response (non-streaming MVP):
```json
{
  "message": { "role": "assistant", "content": "## Zimowa uczta z Kaer Morhen ..." },
  "sources": [
    { "title": "Kaer Morhen", "score": 0.82 },
    { "title": "Venison stew", "score": 0.79 }
  ]
}
```

Streaming (future): same endpoint with `"stream": true` → `text/event-stream` (SSE) emitting incremental tokens, terminated by a final event carrying `sources`.

Error shape (all endpoints):
```json
{ "error": { "code": "CONTEXT_TOO_LARGE", "message": "Request exceeds max context." } }
```

Standard error codes: `VALIDATION_ERROR` (400), `CONTEXT_TOO_LARGE` (413), `RATE_LIMITED` (429, with `Retry-After`), `LLM_UNAVAILABLE` (503), `INTERNAL` (500).

---

## 10. Data Flow (request lifecycle)

```
Client (any language)
  │  POST /api/chat { messages }
  ▼
controller
  │  validate + enforce max-context + rate-limit
  ▼
ChatService
  │  detect query language (util)
  ├─► Embedder.embed(query)                (llm → Ollama nomic-embed-text)
  ├─► rag.search(queryVector, topK)        (cosine over in-memory index)
  │     └─► top-K chunks + scores
  ├─► PromptBuilder.build(history, chunks, answerLanguage)
  ├─► OllamaClient.chat(prompt)            (qwen3:4b; streaming-capable)
  ▼
controller
  │  map to ChatResponse (+ sources)
  ▼
Client  (answer in user's language)
```

---

## 11. RAG Pipeline

**Offline (indexer):**
```
Markdown KB
  → parse (strip frontmatter, keep title/category metadata)
  → chunk (heading-aware; target ~200–400 tokens, small overlap)
  → embed each chunk via Ollama nomic-embed-text (English text)
  → serialize to binary index (index.bin + optional manifest)
```

**Online (server):**
```
load index.bin into memory (once, at startup)
  → embed incoming query (nomic-embed-text)
  → cosine similarity vs all chunk vectors
  → select top-K (K configurable, default ~4–6)
  → apply relevance threshold (RELEVANCE_MIN_SCORE, configurable):
       top score ≥ threshold → GROUNDED path: hand chunks to PromptBuilder
       top score <  threshold → REFUSAL path: pass the best (weak) matches as
         "related suggestions"; PromptBuilder instructs the model to say the
         dish is not in the cookbook and propose those related recipes instead.
```

### Grounding & refusal (no invention)
The service never fabricates dishes absent from the KB. Retrieval decides the path:
- **Grounded:** at least one chunk clears `RELEVANCE_MIN_SCORE` → normal recipe generation strictly from retrieved context.
- **Refusal-with-suggestion:** nothing clears the threshold → the model states the requested dish cannot be cooked from this cookbook and offers the nearest available recipe(s) (by score) as alternatives. Both the threshold and top-K are configurable; the refusal wording adapts to the user's detected language.

### Binary index format (custom, from scratch)
A compact, self-describing file. Illustrative layout:

```
[magic "WCKB"][version u16]
[dim u16]              # embedding dimension (nomic-embed-text = 768)
[count u32]            # number of chunks
repeat count times:
  [idLen u16][id utf8]
  [titleLen u16][title utf8]
  [categoryLen u16][category utf8]
  [textLen u32][text utf8]
  [vector: dim × float32]   # optionally L2-normalized at build time
```
Vectors may be **pre-normalized at build time** so online search reduces to a dot product. Metadata (`title`, `category`, `text`) is stored alongside vectors so the server needs only this one file.

### Language handling
- KB + embeddings: **English** (best retrieval quality for these models).
- Query: embedded as-is; nomic-embed-text provides usable cross-lingual proximity. (If cross-lingual recall proves weak, an optional query-translation step is a future improvement — see §14.)
- Answer language: detected from the user's query; `PromptBuilder` instructs qwen3:4b to answer in that language while grounding on English context.

---

## 12. Directory Structure (proposed)

```
week_6_local_LLM_service/
├── spec.md
├── plan.md
├── CLAUDE.md
├── backend/
│   ├── build.gradle.kts
│   ├── settings.gradle.kts
│   └── src/
│       ├── main/kotlin/com/witchercookbook/
│       │   ├── Application.kt            # Ktor entry point
│       │   ├── config/
│       │   ├── controller/
│       │   ├── service/
│       │   ├── rag/
│       │   ├── prompt/
│       │   ├── llm/
│       │   ├── model/
│       │   ├── util/
│       │   └── indexer/                  # offline main (IndexerApp.kt)
│       └── test/kotlin/com/witchercookbook/
├── knowledge-base/                       # authored Markdown (English)
│   ├── locations/
│   ├── taverns/
│   ├── ingredients/
│   ├── drinks/
│   ├── meals/
│   └── regions/
├── index/
│   └── index.bin                         # generated artifact (not committed if large)
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
└── deploy/
    ├── nginx.conf
    ├── witcher-backend.service           # systemd unit
    └── README.md                         # deployment runbook
```

---

## 13. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | Cross-lingual retrieval (non-English query vs English embeddings) has weak recall. | Poorer grounding. | Ship English-first; add optional query→English translation step later (§14). Measure with sample queries. |
| R-2 | qwen3:4b is small; recipe quality/hallucination varies. | Lower output quality. | Strong system prompt, grounded context, low temperature; keep KB focused. |
| R-3 | Single Ollama backend saturates under concurrency. | Latency spikes / timeouts. | Rate limiting + a bounded request semaphore/queue in front of Ollama; clear 429/503. |
| R-4 | No auth → open endpoint discovered and abused. | Resource abuse. | Rate limit per IP, TLS, non-obvious host; optional shared secret is a trivial later add. |
| R-5 | Index format drift between indexer and server. | Startup failure / bad reads. | Version + magic header; server validates dim/version and fails fast. |
| R-6 | Context/token limits misjudged → Ollama truncation. | Silent bad answers. | Enforce max-context at controller; budget tokens in PromptBuilder (history + context + reserve). |
| R-7 | Embeddings accidentally rebuilt at startup. | Slow/incorrect deploy. | Server has no embedding-build path; only the offline indexer can write the index. |
| R-8 | VPS resource limits (RAM/CPU) for local models. | OOM / slowness. | Document minimum VPS specs; qwen3:4b chosen for small footprint. |

---

## 14. Future Improvements

- **Streaming responses** end-to-end (SSE) to the React UI.
- **Markdown importer** to auto-ingest sources into the KB.
- **Optional query translation** (non-English → English) before retrieval for stronger cross-lingual recall.
- **Optional shared-secret / API key** if the service is opened wider.
- **Retrieval quality tooling**: a small eval set + offline recall scoring.
- **Re-ranking** of top-K (e.g., cross-encoder) if quality demands.
- **Caching** of query embeddings and frequent recipes.
- **Metrics/dashboard** (Prometheus-style counters for latency, rate-limit hits, retrieval scores).
- **Multiple index shards / larger KB** with an on-disk memory-mapped format.

---

## 15. Acceptance Criteria

- **AC-1** `GET /api/health` returns `ok` with `indexLoaded: true` after startup, and the server never rebuilds embeddings.
- **AC-2** `POST /api/chat` returns a Witcher-themed recipe grounded in retrieved KB chunks, with a `sources` list.
- **AC-3** A remote client (different machine) can reach the API over HTTPS. *(NFR-1)*
- **AC-4** The service handles **multiple simultaneous** chat requests correctly (verified with a concurrency test). *(NFR-2)*
- **AC-5** Exceeding the **rate limit** yields HTTP `429` with `Retry-After`. *(NFR-3)*
- **AC-6** Exceeding the **max context** yields HTTP `413 CONTEXT_TOO_LARGE` and does not reach Ollama. *(NFR-4)*
- **AC-7** A query in Russian returns an answer **in Russian**, grounded on English context. *(FR-4)*
- **AC-8** The offline indexer produces `index.bin` from the Markdown KB; the server loads it and reports chunk count.
- **AC-9** Architecture boundaries hold: `rag` has no Ollama import; prompts are assembled only in `PromptBuilder`; `service` has no Ktor import. *(NFR-5)*
- **AC-10** Core units (chunking, cosine search, prompt building, language detection) pass tests **without** a running Ollama. *(NFR-6)*
- **AC-11** The vertical slice (React → Ktor → Ollama → chat) works before RAG is introduced.
- **AC-12** A request for a dish **absent** from the KB (top score below threshold) yields a **refusal-with-suggestion** — the service states it cannot cook that dish and proposes the closest available recipe(s) — instead of inventing one. *(FR-10)*
```

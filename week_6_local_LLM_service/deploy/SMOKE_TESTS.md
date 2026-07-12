# Witcher Cookbook — Acceptance Checklist (spec §15)

Two tiers:

- **Static / offline** — verified in the repo without Ollama or a VPS. Run from
  `backend/` unless noted.
- **Runtime** — needs the deployed service (Ollama + backend + Nginx). Run
  against the VPS after the `deploy/README.md` runbook. Chat-path checks aren't
  run on the dev laptop because `qwen3:4b` inference is too slow there.

Status below reflects the last local pass (Task G1).

---

## Static / offline (verified locally ✓)

### AC-1 — health reports `indexLoaded`, no embedding rebuild
```bash
# Server loads the prebuilt index; startup never chunks/embeds the KB.
java -jar backend/build/libs/witcher-backend.jar &   # from repo root
curl -s localhost:8080/api/health
# → {"status":"ok","indexLoaded":true,"chunks":33}
```
Code check: `Application.kt` imports only `VectorIndex` (calls `.load()`), no
`Chunker`/`MarkdownParser`/`IndexCodec.write`. The `Embedder` on the server path
embeds only the per-request **query**, never the KB. **✓**

### AC-8 — offline indexer builds `index.bin`, server reports chunk count
```bash
cd backend && ./gradlew indexer   # requires Ollama + nomic-embed-text
# → writes index/index.bin, logs chunk count
```
`index/index.bin` present (129 KB, 33 chunks); `indexer` Gradle task registered. **✓**

### AC-9 — architecture boundaries
```bash
cd backend/src/main/kotlin/com/witchercookbook
grep -rn "import" rag/ | grep -iE "ollama|ktor"   # → empty
grep -rn "import io.ktor" service/                # → empty
```
`rag/` has no Ollama/Ktor import; `service/` has no Ktor import; prompts assembled
only in `prompt/PromptBuilder.kt` (service injects and calls it). **✓**

### AC-10 — core units pass without Ollama
```bash
cd backend && ./gradlew test
```
62 tests green: Chunker, MarkdownParser, IndexCodec, SimilaritySearch, VectorMath,
PromptBuilder, LanguageDetector, RateLimiter, LlmConcurrencyGate. None import an
HTTP client / Ollama transport — Ollama-independent by construction. **✓**

### AC-11 — vertical slice preceded RAG
Git history: Tasks A1–A5 (health → config → Ollama client → `/api/chat` → React UI)
landed before Phase C/D RAG. **✓**

---

## Runtime (run on the deployed VPS)

### AC-2 — grounded recipe + `sources`
```bash
curl -sk -X POST https://DOMAIN/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"a hearty winter dinner"}]}'
```
Expect: a Witcher-themed recipe grounded in retrieved chunks + a non-empty
`sources` array (title + score).

### AC-3 — remote HTTPS access
From a **different machine**:
```bash
curl -sk https://DOMAIN/api/health     # 200 ok
```
Open `https://DOMAIN/` in a browser; SPA loads; send a message → recipe renders.

### AC-4 — concurrency
```bash
seq 8 | xargs -P8 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST https://DOMAIN/api/chat -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"a warm stew"}]}'
```
Expect: all `200` (or clean `503 LLM_UNAVAILABLE` under load) — no corruption.
Local proof already exists via `LlmConcurrencyGateTest`.

### AC-5 — rate limit `429` + `Retry-After`
```bash
for i in $(seq 1 40); do
  curl -s -o /dev/null -w "%{http_code} %{header_json}\n" \
    -X POST https://DOMAIN/api/chat -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"user","content":"hi"}]}'
done | sort | uniq -c
```
Expect: `429` responses past the limit, carrying a `Retry-After` header. Limiter
keys on `X-Forwarded-For` (set by Nginx). Local proof: `RateLimiterTest`.

### AC-6 — max context `413`, Ollama not reached
```bash
BIG=$(python3 -c "print('a'*20000)")
curl -sk -o /dev/null -w "%{http_code}\n" -X POST https://DOMAIN/api/chat \
  -H 'Content-Type: application/json' \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$BIG\"}]}"
```
Expect: `413 CONTEXT_TOO_LARGE`; backend logs show the request rejected before the
Ollama call.

### AC-7 — Russian query → Russian answer
```bash
curl -sk -X POST https://DOMAIN/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"сытный зимний ужин"}]}'
```
Expect: answer written in Russian, grounded on the English KB context; `sources`
present.

### AC-12 — refusal-with-suggestion (no invention)
```bash
curl -sk -X POST https://DOMAIN/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"sushi with dragon roll pizza"}]}'
```
Expect: the service states it cannot cook that dish from this cookbook and
proposes the closest available recipe(s) — no fabricated dish. Triggered when the
top similarity score is below `RELEVANCE_MIN_SCORE`.

---

## Summary

| AC | What | Status |
|----|------|--------|
| AC-1  | health + no rebuild        | ✓ local |
| AC-2  | grounded recipe + sources  | ⧗ VPS |
| AC-3  | remote HTTPS               | ⧗ VPS |
| AC-4  | concurrency                | ✓ unit / ⧗ VPS burst |
| AC-5  | rate limit 429             | ✓ unit / ⧗ VPS burst |
| AC-6  | max context 413            | ✓ validation / ⧗ VPS |
| AC-7  | RU query → RU answer       | ⧗ VPS |
| AC-8  | indexer builds index       | ✓ local |
| AC-9  | architecture boundaries    | ✓ local |
| AC-10 | tests without Ollama       | ✓ local (62) |
| AC-11 | vertical slice first       | ✓ history |
| AC-12 | refusal-with-suggestion    | ⧗ VPS |

Local tier passes. Runtime tier (AC-2, 3, 7, 12 + live burst checks for 4–6) is
the deploy-time smoke pass — run it once the VPS is up.

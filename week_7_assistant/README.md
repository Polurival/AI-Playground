# Week 7 — Developer Assistant (RAG + MCP + `/help`)

A project-agnostic developer assistant. Ask it questions about a codebase with `/help` and it
answers from that project's **documentation (RAG)** and its **live git state (MCP)**, citing the
exact doc files it used — and refusing instead of hallucinating when the docs don't cover the
question.

Nothing is hardcoded to one project: the target repo and its doc globs are configuration
(`--repo` on the CLI, `ProjectConfig` in code), so the same assistant works on any git repo with
docs. The examples below use [Typer](https://github.com/fastapi/typer) as the demo target.

---

## 1. Prerequisites

- **Python env** with `mcp`, `sentence-transformers`, `openai`, `requests`. In this repo that is
  `../deepseek-env` (the `hf-env` venv lacks `mcp`).
- **Ollama** running locally, with the embedding model pulled:
  ```bash
  sudo snap start ollama          # the snap service starts disabled
  ollama pull nomic-embed-text    # 768-dim embeddings used for both docs and queries
  ```
- **LLM for generation** — one of:
  - `DEEPSEEK_API_KEY` exported (cloud, the default; fast on a laptop), or
  - a local Ollama chat model for `/model local` (e.g. `qwen2.5:3b` — slower on a laptop).

Cross-encoder reranking downloads `BAAI/bge-reranker-base` on first use (needs network once). If
it can't load, retrieval falls back to plain cosine order — the pipeline still runs.

---

## 2. Setup for the Typer demo

Clone Typer next to this repo (kept outside the repo tree so it stays clean and gives MCP a real
git repo to read):

```bash
git clone --depth 1 https://github.com/fastapi/typer.git \
    /media/polurival/Data/AI-Projects/typer
```

Set a shell shortcut for the right interpreter:

```bash
cd /media/polurival/Data/AI-Projects/AI-Playground/week_7_assistant
PY=../deepseek-env/bin/python
REPO=/media/polurival/Data/AI-Projects/typer
```

---

## 3. Run

### Step 1 — Index the docs (once, or after docs change)

```bash
$PY main.py --repo "$REPO" ingest
```

Reads `README` + `docs/**/*.md` (see globs in `config.py`), splits them into chunks, embeds each,
and stores them in a per-project SQLite index (`rag_typer.db`). Output:

```
Ingested 914 chunks from 'typer' -> .../week_7_assistant/rag_typer.db
```

> Embedding is serial through Ollama — ~12 minutes for Typer's ~914 chunks. One-time cost. Add
> `-v` (before the subcommand: `$PY main.py --repo "$REPO" -v ingest`) to watch progress.

### Step 2a — Ask one question

```bash
$PY main.py --repo "$REPO" help "How do I define an optional CLI argument with a default value?"
```

```
This makes `name` an optional CLI argument with a default value of "World"
(docs/tutorial/arguments/optional.md).
...
Sources:
  - docs/tutorial/arguments/optional.md :: Optional CLI Arguments > Make an optional *CLI argument* (cosine=0.694, rerank=0.979)
  - docs/tutorial/arguments/default.md   :: CLI Arguments with Default > An optional *CLI argument* with a default (cosine=0.734, rerank=0.949)
  ...
[provider: deepseek (deepseek-chat, cloud) | rewritten: 'define optional CLI argument default value Typer' | max_cosine: 0.781]
```

### Step 2b — Interactive session

```bash
$PY main.py --repo "$REPO"
```

```
Developer assistant for 'typer'  (docs: .../rag_typer.db)
Provider: deepseek (deepseek-chat, cloud)  |  available: ['deepseek', 'local']
Commands: /help <question>  /branch  /diff  /model <local|deepseek>  /quit

typer> /branch
branch: master

typer> /help how do I install shell completion?
Run `your-cli-app --install-completion` ... (docs/tutorial/typer-app.md)
Sources:
  - docs/tutorial/typer-app.md   :: Typer App > CLI application completion (cosine=0.739, rerank=0.893)
  - docs/contributing.md         :: Development - Contributing > Completion (cosine=0.724, rerank=0.660)
  ...

typer> /model local        # switch generation to a local Ollama model
switched -> local (qwen2.5:3b, Ollama @ http://localhost:11434/v1)

typer> /quit
```

REPL commands:

| Command | Action |
|---|---|
| `/help <question>` (or bare text) | answer a question about the project |
| `/branch` | current git branch, live via MCP |
| `/diff` | git context including the uncommitted diff |
| `/model <local\|deepseek>` | switch the LLM backend |
| `/quit` | exit |

### Out-of-scope questions are refused

```bash
$PY main.py --repo "$REPO" help "What is the airspeed velocity of an unladen swallow?"
```

```
I couldn't find anything in typer's documentation relevant enough to answer that. ...
[provider: deepseek (deepseek-chat, cloud) | rewritten: 'airspeed velocity unladen swallow' | max_cosine: 0.516]
```

`max_cosine 0.516 < 0.55` threshold → the generation LLM is **never called**, so it can't invent
an answer.

---

## 4. How the assistant works (step by step)

```
/help <question>
  1. Query rewrite        assistant.py  _rewrite()
  2. Embed query          rag.py        embed_query()      (nomic-embed-text, "search_query:" prefix)
  3. Broad recall         rag.py        cosine top-12      (reuses retrieval.cosine_similarity)
  4. Hard threshold       rag.py        best cosine >= 0.55 ? continue : REFUSE (no LLM call)
  5. Rerank               rag.py        cross-encoder -> top-4 (reuses retrieval_v2)
  6. Git context (MCP)    git_context.py branch/status/log/(files/diff) via git MCP server
  7. Grounded answer      assistant.py  LLM over doc excerpts + git context (DeepSeek or local)
  8. Answer + citations   main.py       print answer, source files, diagnostics
```

1. **Query rewrite** — the raw question is rewritten into a dense search query, keeping code
   identifiers/file names verbatim (e.g. *"how do I make an arg optional?"* →
   *"define optional CLI argument default value Typer"*). If it's already good, it's left as-is.

2. **Embed query** — the rewritten query is embedded with Ollama `nomic-embed-text`, prefixed
   `search_query:`. Ingest embeds documents with the matching `search_document:` prefix — the two
   prefixes are what this model needs for good doc↔query matching.

3. **Broad recall** — cosine similarity against all chunk embeddings in `rag_<name>.db`, take the
   top 12 candidates.

4. **Hard relevance threshold** — if the *best* candidate's cosine is below `0.55`, retrieval
   aborts here. The assistant returns a canned "not in the docs" refusal and **never calls the
   generation LLM**, so an off-topic question can't produce a made-up answer.

5. **Cross-encoder rerank** — the survivors are re-scored by `BAAI/bge-reranker-base`, which
   judges (query, chunk) relevance directly, and the top 4 are kept. (Notice in the examples how
   `rerank` reorders chunks that had similar `cosine` scores.)

6. **Live git context via MCP** — `git_context.py` starts the git MCP server from
   `../week_4_mcp/day_17_create_mcp` as a subprocess (stdio) and calls its tools:
   `git_current_branch` (the assignment's minimum), plus `git_status`, `git_log`, and optionally
   `git_ls_files` / `git_diff`. This is why `/help` can answer *"what branch am I on?"* or fold
   the current branch/commit into a structural answer.

7. **Grounded answer** — the kept doc excerpts **and** the git context are packed into one prompt
   with a strict system instruction (answer only from this material, cite the source files). The
   call goes through `llm_provider`, so it runs on DeepSeek (cloud) or a local Ollama model.

8. **Answer + citations** — the answer is printed with its source files, the rewritten query, the
   active provider, and the max cosine score for transparency.

---

## 5. Files

| File | Role |
|---|---|
| `config.py` | `ProjectConfig` — repo path, doc globs, db/table (all project-specific data) |
| `doc_loader.py` | walk repo → read docs → split Markdown by heading into chunks |
| `ingest.py` | embed chunks (`search_document:` prefix) → per-project SQLite index |
| `rag.py` | embed query → cosine recall → hard threshold → cross-encoder rerank |
| `git_context.py` | live git facts over MCP (branch / status / log / files / diff) |
| `assistant.py` | `/help` orchestration + grounded generation |
| `main.py` | CLI: `ingest`, `help`, interactive REPL |
| `_bootstrap.py` | wires `sys.path` to the reused week_4 / week_5 modules |

## 6. Reuse from earlier weeks (nothing re-implemented)

- **`week_5_RAG`** — `database` (SQLite chunk store), `embedder` (Ollama `nomic-embed-text`),
  `retrieval.cosine_similarity`, `retrieval_v2.rerank_with_cross_encoder`,
  `chat_with_RAG/llm_provider` (DeepSeek ↔ local Ollama switch).
- **`week_4_mcp/day_17_create_mcp`** — the git MCP server/client over stdio. Two additive tools
  were added there for this assistant: `git_current_branch`, `git_ls_files`.

## 7. Point it at another project

```bash
$PY main.py --repo /path/to/OTHER/repo ingest
$PY main.py --repo /path/to/OTHER/repo help "..."
```

Each project gets its own index `rag_<name>.db`. Adjust the corpus via `DEFAULT_DOC_GLOBS` in
`config.py` or by constructing a custom `ProjectConfig`.


### 8. Stop Ollama

```bash
sudo pkill ollama
```
# Week 7 — PR Auto-Review (AI code review on every Pull Request)

An AI reviewer that runs in CI on each Pull Request. It gets the PR **diff**, pulls related
repository context with **RAG over the repo's documentation _and_ code**, and posts a structured
review as a PR comment:

- 🐞 **Потенциальные баги** (potential bugs)
- 🏛️ **Архитектурные проблемы** (architecture issues)
- 💡 **Рекомендации** (recommendations)

## Universal by design

Unlike [`week_7_assistant`](../week_7_assistant) (which reuses the week_5 RAG engines via
`sys.path`), this package is **deliberately standalone** — it carries its own tiny SQLite vector
store, cosine search, CPU embeddings, and OpenAI-compatible LLM client, and depends only on
`openai` + `sentence-transformers`. Drop it into **any** git repo, add the workflow and one secret,
and PR reviews start working. No Ollama, no local server, nothing hardcoded to this repo.

---

## How it works

```
Pull Request
  1. Checkout + base...head diff   review_pr.py        (git diff, three-dot = the PR's own changes)
  2. Parse the diff               diff_parser.py       per-file hunks, added/removed lines
  3. Build RAG index              index.py + corpus.py docs + code -> chunks -> CPU embeddings -> SQLite
  4. Retrieve context             retrieve.py          per changed file: path + added lines -> top-k chunks
  5. Generate the review          reviewer.py + llm.py diff + retrieved context -> LLM -> 3-section review
  6. Post / update PR comment     workflow (gh)        upsert one comment (no spam on re-push)
```

RAG here is **supplementary**: even if retrieval finds nothing relevant, the diff itself is always
reviewed (the reviewer never refuses — that differs from the `/help` assistant's hard threshold).

## Files

| File | Role |
|---|---|
| `config.py` | `ReviewConfig` — repo, index path, corpus/exclude rules, model + retrieval knobs (env-driven) |
| `corpus.py` | walk repo → chunk **docs + code** (Markdown by heading, code by line window) |
| `embeddings.py` | CPU `sentence-transformers` embeddings (default `all-MiniLM-L6-v2`, no server) |
| `store.py` | standalone SQLite vector store |
| `index.py` | corpus → embeddings → store (rebuilt fresh each run) |
| `retrieve.py` | embed query → cosine top-k over the index |
| `diff_parser.py` | unified diff → structured per-file changes (pure stdlib) |
| `llm.py` | OpenAI-compatible chat client (DeepSeek / OpenAI / any gateway) |
| `reviewer.py` | orchestration + review prompt (RU/EN) |
| `review_pr.py` | CLI entry point |
| `../.github/workflows/pr-autoreview.yml` | the GitHub Action |

---

## Enable it on this repo

1. Add a repository secret **`DEEPSEEK_API_KEY`** (Settings → Secrets and variables → Actions).
   `OPENAI_API_KEY` works too — see *Point it at another provider* below.
2. That's it. `.github/workflows/pr-autoreview.yml` triggers on `opened` / `reopened` /
   `synchronize` and comments the review on the PR.

> Fork PRs are skipped by design: forks get a read-only token and no secrets, so a review can't
> run or post. Reviews run on branches pushed to this repo.

## Enable it on ANY other repo

Copy two things into the target repo and add the secret:

```
your-repo/
├── .github/workflows/pr-autoreview.yml
└── week_7_PR_autoreview/          # this whole folder
```

Nothing else is repo-specific. The corpus is whatever docs/code the checkout contains.

---

## Run it locally

```bash
pip install -r week_7_PR_autoreview/requirements.txt
export DEEPSEEK_API_KEY=sk-...

# Review the current branch against main, for any repo on disk:
python week_7_PR_autoreview/review_pr.py \
    --repo /path/to/repo --base origin/main --head HEAD --out review.md -v

# Or feed a pre-computed diff (stdin):
git -C /path/to/repo diff main...HEAD | \
    python week_7_PR_autoreview/review_pr.py --repo /path/to/repo --diff-file - -v
```

The review is written to `--out` and printed to stdout.

### CLI flags

| Flag | Meaning |
|---|---|
| `--repo` | repo to review (default: cwd) |
| `--base` / `--head` | refs/SHAs for `git diff base...head` (`--head` defaults to `HEAD`) |
| `--diff-file` | read a unified diff from a file (`-` = stdin) instead of running git |
| `--out` | output markdown path (default `review.md`) |
| `--lang` | `ru` (default) or `en` |
| `--no-index` | reuse an existing index instead of rebuilding |
| `-v` | verbose logging |

---

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `AUTOREVIEW_LLM_API_KEY` | — | LLM key (first one found wins) |
| `AUTOREVIEW_LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible endpoint |
| `AUTOREVIEW_LLM_MODEL` | `deepseek-chat` | generation model |
| `AUTOREVIEW_EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | CPU embedder |
| `AUTOREVIEW_LANG` | `ru` | review language (`ru`/`en`) |
| `AUTOREVIEW_TOP_K` | `4` | chunks retrieved per changed file |
| `AUTOREVIEW_MAX_CTX` | `10` | context chunks after de-dup |
| `AUTOREVIEW_MAX_DIFF` | `16000` | diff char budget in the prompt |

### Point it at another provider

OpenAI:

```bash
export OPENAI_API_KEY=sk-...
export AUTOREVIEW_LLM_BASE_URL=https://api.openai.com/v1
export AUTOREVIEW_LLM_MODEL=gpt-4o-mini
```

Any OpenAI-compatible gateway (vLLM, OpenRouter, a local server, …) works the same way — set the
base URL, model, and key.

---

## Notes & limits

- The index is rebuilt fresh each run so it always matches the exact code under review. For a
  single repo this takes seconds on CPU; for very large repos, tune the exclude lists in
  `config.py` or cap the corpus.
- Very large diffs are truncated to `AUTOREVIEW_MAX_DIFF` chars in the prompt.
- One comment per PR: repeated pushes **update** the same comment (via a hidden
  `<!-- ai-autoreview -->` marker) instead of adding new ones.

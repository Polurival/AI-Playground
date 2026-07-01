# Week 5 — RAG Document Indexing Pipeline

Local RAG (Retrieval-Augmented Generation) indexing pipeline for *Alice's Adventures in Wonderland*. Parses an EPUB, applies two chunking strategies, generates embeddings via Ollama, and stores everything in SQLite.

---

## Project Structure

```
week_5_RAG/
├── main.py           # Entry point — runs the full pipeline
├── epub_parser.py    # EPUB → list of chapters (text + title)
├── chunkers.py       # Two chunking strategies
├── embedder.py       # Ollama nomic-embed-text embeddings
├── database.py       # SQLite storage (rag_wonderland.db)
├── analysis.py       # Comparison report
└── Alice's_Adventures_in_Wonderland_by_Lewis_Carroll.3.epub
```

---

## How It Works

### Step 1 — EPUB Parsing (`epub_parser.py`)

An EPUB file is a ZIP archive. Inside `OEBPS/` there are numbered XHTML files — one per chapter. The parser:

1. Opens the ZIP with `zipfile`
2. Sorts XHTML files numerically (so chapter 2 comes before chapter 10)
3. Strips all HTML tags with `BeautifulSoup`
4. Extracts chapter titles from `<h2>` tags (falls back to `<h1>`, `<title>`)
5. Returns a list of dicts: `{filename, title, text}`

```
ch00 [  579 chars] Alice's Adventures in Wonderland   ← title page
ch01 [11575 chars] CHAPTER I. Down the Rabbit-Hole
ch02 [10963 chars] CHAPTER II. The Pool of Tears
...
ch12 [11653 chars] CHAPTER XII. Alice's Evidence
```

### Step 2 — Chunking (`chunkers.py`)

Two strategies are implemented:

**Fixed-size chunking** — splits text into 1000-character windows with 180-character overlap (~18%). Overlap preserves context at chunk boundaries so a sentence cut in half doesn't lose its tail.

```
[  0 – 1000 ]  chunk 0
[ 820 – 1820 ]  chunk 1   ← 180 chars overlap with chunk 0
[1640 – 2640 ]  chunk 2
...
```

**Structural chunking** — treats each XHTML file (chapter) as one natural chunk. If a chapter exceeds 4000 characters, it is split at paragraph boundaries (`\n\n`), keeping the chapter title in metadata for every sub-chunk.

| | Fixed-size | Structural |
|---|---|---|
| Total chunks | 183 | 44 |
| Avg length | ~957 chars | ~3288 chars |
| Min length | 52 chars | 52 chars |
| Max length | 1000 chars | 4000 chars |

### Step 3 — Metadata Enrichment

Every chunk carries a metadata dict:

```python
{
    "chunk_id":    "fixed_ch01_003",          # strategy_chNN_NNN
    "text":        "Alice was beginning...",
    "meta_source": "Alice's_Adventures_in_Wonderland_by_Lewis_Carroll.3.epub",
    "meta_file":   "6517791129234588483_11-h-1.htm.xhtml",
    "meta_section": "CHAPTER I. Down the Rabbit-Hole",
}
```

### Step 4 — Embeddings (`embedder.py`)

Calls the local Ollama API with model `nomic-embed-text` (768-dimensional vectors):

```
POST http://localhost:11434/api/embeddings
{"model": "nomic-embed-text", "prompt": "<chunk text>"}
```

If Ollama is not running, the function logs a warning and stores `null` — the rest of the pipeline continues. Embeddings are added to each chunk dict as `"embedding": json.dumps(vector)`.

### Step 5 — SQLite Storage (`database.py`)

Creates `rag_wonderland.db` with two tables:

```sql
CREATE TABLE chunks_fixed (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id     TEXT NOT NULL UNIQUE,
    text         TEXT NOT NULL,
    meta_source  TEXT,
    meta_file    TEXT,
    meta_section TEXT,
    embedding    TEXT    -- JSON array: "[0.12, -0.34, ...]" or null
);

-- identical schema for chunks_structural
```

Embeddings are serialized with `json.dumps()` on write and `json.loads()` on read, since SQLite has no native vector type.

### Step 6 — Comparison Report (`analysis.py`)

Prints a table comparing both strategies plus a prose analysis of which approach suits literary text better.

---

## Quick Start

### 1. Install dependencies

```bash
../deepseek-env/bin/pip install beautifulsoup4 lxml
# pip install beautifulsoup4 lxml
# requests is used for Ollama — usually pre-installed
```

### 2. Start Ollama (for embeddings)

```bash
ollama serve                      # start the Ollama server
ollama pull nomic-embed-text      # download the embedding model (~270 MB)
```

### 3. Run the pipeline

```bash
source ../deepseek-env/bin/activate
python3 main.py
```

### 4. Stop Ollama

```bash
sudo pkill ollama
```

Expected output (with Ollama running):

```
18:14:01  INFO  Parsing EPUB: Alice's_Adventures_in_Wonderland_by_Lewis_Carroll.3.epub
18:14:01  INFO  Extracted 14 chapters
18:14:01  INFO  Creating fixed-size chunks (1000 chars, 180 overlap) …
18:14:01  INFO  Fixed-size: 183 chunks
18:14:01  INFO  Creating structural chunks (chapter-based, max 4000 chars) …
18:14:01  INFO  Structural: 44 chunks
18:14:01  INFO  [fixed] embedding 1/183
18:14:08  INFO  [fixed] embedding 10/183
...
18:15:30  INFO  All data saved to rag_wonderland.db

============================================================
  CHUNKING STRATEGY COMPARISON REPORT
============================================================
...
```

Without Ollama running, the pipeline still completes — embeddings are stored as `null` and can be backfilled later.

---

## Usage Examples

### Parse only

```python
from epub_parser import parse_epub

chapters = parse_epub()
for ch in chapters:
    print(ch["title"], "—", len(ch["text"]), "chars")
```

### Chunk only

```python
from epub_parser import parse_epub
from chunkers import fixed_chunks, structural_chunks

chapters = parse_epub()
fixed  = fixed_chunks(chapters)        # default: 1000 chars, 180 overlap
struct = structural_chunks(chapters)   # default: max 4000 chars per chunk

print(f"Fixed: {len(fixed)} chunks")
print(f"Structural: {len(struct)} chunks")

# Custom chunk size
big_fixed = fixed_chunks(chapters, size=500, overlap=75)
```

### Get a single embedding

```python
from embedder import get_embedding

vec = get_embedding("Who is Alice?")
if vec:
    print(f"Embedding dim: {len(vec)}")   # 768
    print(f"First values: {vec[:5]}")
else:
    print("Ollama not running")
```

### Query the database

```python
import sqlite3, json

conn = sqlite3.connect("rag_wonderland.db")

# List all chapters in structural chunks
rows = conn.execute(
    "SELECT DISTINCT meta_section FROM chunks_structural"
).fetchall()
for r in rows:
    print(r[0])

# Get all text from Chapter I (fixed-size chunks)
rows = conn.execute(
    "SELECT chunk_id, text FROM chunks_fixed WHERE meta_section LIKE '%CHAPTER I%'"
).fetchall()
for chunk_id, text in rows:
    print(f"\n--- {chunk_id} ---")
    print(text[:200])

# Read an embedding back
row = conn.execute(
    "SELECT chunk_id, embedding FROM chunks_fixed WHERE embedding IS NOT NULL LIMIT 1"
).fetchone()
if row:
    chunk_id, emb_json = row
    vector = json.loads(emb_json)
    print(f"{chunk_id}: {len(vector)}-dim vector")

conn.close()
```

### Simple cosine similarity search

```python
import sqlite3, json, math
from embedder import get_embedding

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0

query = "What did Alice find at the bottom of the rabbit hole?"
q_vec = get_embedding(query)

conn = sqlite3.connect("rag_wonderland.db")
rows = conn.execute(
    "SELECT chunk_id, meta_section, text, embedding FROM chunks_structural "
    "WHERE embedding IS NOT NULL"
).fetchall()
conn.close()

results = []
for chunk_id, section, text, emb_json in rows:
    vec = json.loads(emb_json)
    score = cosine(q_vec, vec)
    results.append((score, chunk_id, section, text))

results.sort(reverse=True)
print(f"Query: {query}\n")
for score, chunk_id, section, text in results[:3]:
    print(f"[{score:.4f}] {chunk_id} — {section}")
    print(text[:300])
    print()
```

---

## Design Notes

**Why JSON for embeddings?** SQLite has no native vector column. `json.dumps()` is simple and portable; for production use, consider [sqlite-vss](https://github.com/asg017/sqlite-vss) or a dedicated vector DB (Chroma, Qdrant, pgvector).

**Why 180-char overlap?** ~18% of 1000 chars. Standard RAG practice uses 10–20% overlap to avoid losing context at chunk cuts without excessive duplication.

**Why structural chunks top out at 4000 chars?** `nomic-embed-text` has an 8192-token context. At ~4 chars/token, 4000 chars ≈ 1000 tokens — comfortably within limits and keeps chunks semantically dense.

**Fixed vs Structural for literary text:** Structural wins for Q&A over narrative — whole scenes and dialogues stay together. Fixed-size is better when retrieval needs fine-grained passage matching (e.g., "find the exact sentence where Alice drinks the potion").

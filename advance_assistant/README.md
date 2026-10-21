# Advance Assistant — general-purpose AI assistant

One assistant, many jobs: answers questions from its own knowledge, **searches the web**, **reads
pages**, **creates / edits / searches files**, does exact **math** and knows the **date**. The model
decides itself which tools to use for each message and chains them (search → fetch → write note).

Built from the patterns of the week_7 projects, minus RAG:

| Borrowed from | What |
|---|---|
| `week_7_file_assistant` | own **MCP server** over stdio, path-traversal guard (`_safe_path`), goal-driven tool loop, anti-"I saved it" hallucination rule |
| `week_7_PR_autoreview` | **standalone** package (only `openai` + `mcp`), OpenAI-compatible client, env-driven config |
| `week_7_assistant` | CLI shape: one-shot command + interactive REPL with slash commands |

Differences: **native function calling** (tool schemas are discovered from the MCP server — adding a
tool = one `@mcp.tool()` function), one persistent MCP session per run, **conversation memory** in chat mode.

## Architecture

```
main.py (CLI / REPL)
  └─ agent.py        tool-calling loop: LLM -> tool_calls -> MCP -> observations -> LLM ... -> answer
       ├─ llm.py         OpenAI-compatible async client (DeepSeek by default)
       └─ mcp_client.py  spawns mcp_server.py, converts MCP tools -> OpenAI tool schemas
            └─ mcp_server.py  FastMCP stdio server
                 ├─ web_tools.py   web_search (DuckDuckGo, no key), fetch_url (HTML -> text)
                 ├─ file_tools.py  list/read/search/write, confined to the workspace
                 └─ misc_tools.py  calculate (safe AST evaluator), current_datetime
```

## Tools

| Tool | Purpose |
|---|---|
| `web_search(query, max_results)` | DuckDuckGo results: title, URL, snippet |
| `fetch_url(url, max_chars)` | readable text of a web page |
| `list_files(glob)` / `read_file(path)` / `search_files(pattern, glob)` | explore the workspace |
| `write_file(path, content, append)` | create / overwrite / append (not registered with `--read-only`) |
| `calculate(expression)` | exact arithmetic (`sqrt`, `log`, `**`, …) — no `eval` |
| `current_datetime()` | local date, time, weekday |

## Setup

```bash
pip install -r requirements.txt            # openai, mcp   (repo: deepseek-env already has both)
export DEEPSEEK_API_KEY=sk-...             # or ASSISTANT_LLM_API_KEY / OPENAI_API_KEY
```

No other keys: web search needs none.

## Usage

```bash
PY=../deepseek-env/bin/python              # or plain python3 after pip install
cd advance_assistant
```

### One-shot questions

```bash
# plain knowledge — no tools used
$PY main.py ask "Explain the difference between a process and a thread"

# math + clock
$PY main.py ask "Сколько будет 17.5% от 2480, и какой сегодня день недели?"

# fresh facts from the web (search -> fetch -> answer with source URLs)
$PY main.py ask "What is the latest stable Python version and what's new in it?"

# web + file creation in one request
$PY main.py ask "Найди в вебе последнюю стабильную версию Python и сохрани краткую заметку в notes/python.md"

# work with your own files
$PY main.py --workspace ~/notes ask "Find every TODO in my notes and make todo.md with a checklist"
$PY main.py --workspace ~/notes --read-only ask "Summarize the notes about the project"

# English replies, more tool rounds, hide the tool trace
$PY main.py --lang en --max-steps 15 ask -q "Compare the top 3 results for 'FastMCP tutorial'"
```

Sample output (tool trace, then the answer):

```
  ⚙ web_search(query=latest stable Python version release)
  ⚙ fetch_url(url=https://www.python.org/downloads/latest/, max_chars=3000)
  ⚙ write_file(path=notes/python.md, content=# Последняя стабильная версия Python\n\n**Python 3.15...)

**Последняя стабильная версия — Python 3.15.0** ...
Заметка сохранена: `notes/python.md`
Источники: https://www.python.org/downloads/latest/ ...
```

### Interactive chat (keeps history, so follow-ups work)

```text
$ $PY main.py
you> Найди в workspace файлы про python
  ⚙ search_files(pattern=(?i)python)
  ⚙ read_file(path=notes/python.md)
В workspace только один файл про Python: notes/python.md ...
you> а сколько в нём строк?
  ⚙ calculate(expression=31)
В файле notes/python.md — 31 строка.
you> /quit
```

Chat commands: `/tools` list tools · `/reset` clear history · `/trace on|off` · `/quit`.

### Inspect the MCP tools

```bash
$PY main.py tools
```

## Options

| Flag / env | Default | Meaning |
|---|---|---|
| `--workspace DIR` | `./workspace` (gitignored) | the only directory file tools can touch |
| `--read-only` | off | `write_file` isn't even offered to the model |
| `--max-steps N` | 10 | tool-call rounds per message; at the limit the model must answer with what it has |
| `--lang ru\|en` / `ASSISTANT_LANG` | `ru` | reply language (the user's own language wins) |
| `-v` | off | agent logs |
| `ASSISTANT_LLM_MODEL` | `deepseek-chat` | model id |
| `ASSISTANT_LLM_BASE_URL` | `https://api.deepseek.com` | any OpenAI-compatible endpoint with tool calling |

Other provider example:
`ASSISTANT_LLM_BASE_URL=https://api.openai.com/v1 ASSISTANT_LLM_MODEL=gpt-4o-mini OPENAI_API_KEY=... $PY main.py`

## Safety notes

- File tools cannot leave the workspace (`../` and symlink escapes are rejected). There is no delete tool.
- Overwrites return a unified diff in the tool result; use `--read-only` for no writes at all.
- Web content is untrusted text fed to the model — pages can contain prompt injection. The assistant
  has no shell and no access outside the workspace, which limits the blast radius.
- `web_search` scrapes DuckDuckGo's HTML page; it may be rate-limited or change markup
  (the tool then returns `error: ...` and the model reports it). Swap in a search API inside
  `web_tools.web_search` if you need reliability.

## Extending

Add a function to `mcp_server.py`:

```python
@mcp.tool()
def my_tool(arg: str) -> str:
    """One-line description the model will see.

    Args:
        arg: what it means.
    """
    ...
```

Restart — the assistant sees it automatically (type hints + docstring become the tool schema).
Next step (RAG was skipped on purpose): add a `rag_search` tool the same way.

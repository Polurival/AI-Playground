#!/usr/bin/env python3

#######################################
# Local LLM chat via Ollama (OpenAI-compatible HTTP API)
#
# Analogous to test_deepseek_task_2.py, but instead of the remote DeepSeek
# API it talks to a LOCAL model served by Ollama. No API key, no network,
# no cloud — everything runs on this laptop.
#
# Tuned for the "short factual Q&A" use case: low temperature, small
# max-tokens cap, and a system prompt that forces terse, no-filler answers.
# Override with --temperature/--max-tokens/--system if you need a different
# case. See benchmark.py for a before/after comparison against the untuned
# generic-assistant config.
#
# Default model is `qwen2.5-3b-qa`, a local derivative of qwen2.5:3b built
# from Modelfile (same weights, no re-download — see Modelfile). It bakes
# in num_ctx=1024 and the factual-Q&A system prompt as the model's defaults.
# Why baked in rather than a --ctx flag: Ollama's OpenAI-compatible /v1
# endpoint (used here via the openai SDK) does not honor per-request num_ctx
# passed through extra_body in this Ollama version (0.24.0) — verified
# against `ollama ps`, whose CONTEXT column ignored the override. The
# native /api/chat endpoint does honor it, but a derived model works
# through either endpoint. Build it with:
#   cp Modelfile ~/qwen_qa.Modelfile && ollama create qwen2.5-3b-qa -f ~/qwen_qa.Modelfile && rm ~/qwen_qa.Modelfile
# (copy via $HOME because the Ollama snap can't read paths outside it, e.g.
# /media/... — no `removable-media` interface connected.)
#
# --- One-time setup -----------------------------------------------------
# Install Ollama (already present here as a snap):
#   sudo snap install ollama            # or: curl -fsSL https://ollama.com/install.sh | sh
#
# Start the local server (listens on http://localhost:11434):
#   sudo snap start ollama              # snap build runs as a system daemon
#   # or, non-snap build:  ollama serve
#
# Pull the model (~1.9 GB, one-time download):
#   ollama pull qwen2.5:3b
#
# --- Reuse the existing virtualenv (has the openai SDK) -----------------
#   source ../deepseek-env/bin/activate
#
# --- Usage examples -----------------------------------------------------
# Basic question (default: Hello) — uses the qwen2.5-3b-qa derived model:
# ctx=1024, temp=0.2, max_tokens=150, factual-only system prompt
#   python3 local_llm_chat.py
#
# Custom question
#   python3 local_llm_chat.py "What is the capital of Japan?"
#
# Override for a different case (e.g. longer, more creative output)
#   python3 local_llm_chat.py "Tell me a short story" --max-tokens 500 --temperature 0.9
#
# Explicit response format (added to system prompt)
#   python3 local_llm_chat.py "What is Docker?" --format "Answer in exactly 3 bullet points"
#
# Revert to the untuned base model + generic assistant prompt
#   python3 local_llm_chat.py "What is Docker?" --model qwen2.5:3b --system "You are a helpful assistant" --temperature 0.7 --max-tokens 500
#
# Stop sequence (use --stop=VALUE if VALUE starts with "-")
#   python3 local_llm_chat.py "Explain recursion briefly" --max-tokens 300 --stop=---END---
#
# Swap the model or endpoint
#   python3 local_llm_chat.py "Hi" --model llama3.2:3b
#   python3 local_llm_chat.py "Hi" --base-url http://localhost:11434/v1
#
# Run the before/after benchmark (quality, speed, RAM)
#   python3 benchmark.py
#######################################

import argparse
import sys

from openai import OpenAI

parser = argparse.ArgumentParser(
    description="Ask questions to a LOCAL LLM served by Ollama (OpenAI SDK)"
)
parser.add_argument(
    "question",
    nargs="?",
    default="Hello",
    help="Your question for the local model (default: Hello)",
)
parser.add_argument(
    "--model",
    type=str,
    default="qwen2.5-3b-qa",
    help="Local model name as shown by `ollama list` (default: qwen2.5-3b-qa, "
    "a Modelfile derivative of qwen2.5:3b tuned for factual Q&A — see Modelfile)",
)
parser.add_argument(
    "--base-url",
    type=str,
    default="http://localhost:11434/v1",
    help="Ollama OpenAI-compatible endpoint (default: http://localhost:11434/v1)",
)
parser.add_argument(
    "--max-tokens",
    type=int,
    default=150,
    help="Maximum tokens in response (default: 150, tuned for short factual answers)",
)
parser.add_argument(
    "--temperature",
    type=float,
    default=0.2,
    help="Creativity level 0-1 (default: 0.2, tuned for deterministic factual answers)",
)
parser.add_argument(
    "--system",
    type=str,
    default=None,
    help="Override the model's built-in system prompt. Default: none — "
    "qwen2.5-3b-qa already has a factual-Q&A system prompt baked in via "
    "Modelfile, so no message is sent unless this is set.",
)
parser.add_argument(
    "--format",
    type=str,
    default=None,
    help="Explicit response format description (added to system prompt)",
)
parser.add_argument(
    "--stop",
    action="append",
    default=None,
    metavar="SEQUENCE",
    help="Stop sequence (repeatable). If value starts with '-', use --stop=VALUE",
)
args = parser.parse_args()

messages = []
if args.system or args.format:
    # Falls back to the model's own Modelfile SYSTEM prompt when neither
    # --system nor --format is given (Ollama applies it automatically to
    # any request that omits a system message).
    system_content = args.system or "You are a helpful assistant"
    if args.format:
        system_content += f"\n\nResponse format requirements:\n{args.format}"
    messages.append({"role": "system", "content": system_content})
messages.append({"role": "user", "content": args.question})

# Ollama ignores the API key, but the OpenAI SDK requires a non-empty value.
client = OpenAI(
    api_key="ollama",
    base_url=args.base_url,
)

request_kwargs = {
    "model": args.model,
    "messages": messages,
    "stream": False,
    "max_tokens": args.max_tokens,
    "temperature": args.temperature,
}
if args.stop:
    request_kwargs["stop"] = args.stop

print(f"Model: {args.model}  (local, via {args.base_url})")
print(f"Q: {args.question}")
if args.format:
    print(f"Format: {args.format}")
print(f"max_tokens={args.max_tokens}, temperature={args.temperature}", end="")
if args.stop:
    print(f", stop={args.stop!r}", end="")
print("\n")
print("A: ", end="", flush=True)

try:
    response = client.chat.completions.create(**request_kwargs)
except Exception as e:
    print()
    print(f"Error: could not reach the local model: {e}", file=sys.stderr)
    print(
        "Is Ollama running?  Start it with `sudo snap start ollama` "
        "(or `ollama serve`) and pull the model with `ollama pull "
        f"{args.model}`.",
        file=sys.stderr,
    )
    sys.exit(1)

print(response.choices[0].message.content)

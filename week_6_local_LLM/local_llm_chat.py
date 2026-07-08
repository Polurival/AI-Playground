#!/usr/bin/env python3

#######################################
# Local LLM chat via Ollama (OpenAI-compatible HTTP API)
#
# Analogous to test_deepseek_task_2.py, but instead of the remote DeepSeek
# API it talks to a LOCAL model served by Ollama. No API key, no network,
# no cloud — everything runs on this laptop.
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
# Basic question (default: Hello)
#   python3 local_llm_chat.py
#
# Custom question
#   python3 local_llm_chat.py "What is Python?"
#
# Control length + creativity
#   python3 local_llm_chat.py "Tell me a short story" --max-tokens 500 --temperature 0.9
#
# More focused answer
#   python3 local_llm_chat.py "List 5 facts about Python" --temperature 0.3
#
# Explicit response format (added to system prompt)
#   python3 local_llm_chat.py "What is Docker?" --format "Answer in exactly 3 bullet points"
#
# Stop sequence (use --stop=VALUE if VALUE starts with "-")
#   python3 local_llm_chat.py "Explain recursion briefly" --max-tokens 300 --stop=---END---
#
# Swap the model or endpoint
#   python3 local_llm_chat.py "Hi" --model llama3.2:3b
#   python3 local_llm_chat.py "Hi" --base-url http://localhost:11434/v1
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
    default="qwen2.5:3b",
    help="Local model name as shown by `ollama list` (default: qwen2.5:3b)",
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
    default=500,
    help="Maximum tokens in response (default: 500)",
)
parser.add_argument(
    "--temperature",
    type=float,
    default=0.7,
    help="Creativity level 0-1 (default: 0.7)",
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

system_content = "You are a helpful assistant"
if args.format:
    system_content += f"\n\nResponse format requirements:\n{args.format}"

# Ollama ignores the API key, but the OpenAI SDK requires a non-empty value.
client = OpenAI(
    api_key="ollama",
    base_url=args.base_url,
)

request_kwargs = {
    "model": args.model,
    "messages": [
        {"role": "system", "content": system_content},
        {"role": "user", "content": args.question},
    ],
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

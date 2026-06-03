#!/usr/bin/env python3

#######################################
# Install venv if not already installed
# sudo apt install python3-venv

# Create a virtual environment
# python3 -m venv deepseek-env

# Activate it
# source deepseek-env/bin/activate

# Now pip works normally
# pip install openai

# Set API key
# export DEEPSEEK_API_KEY='your-key-here'

# Test your DeepSeek script
# python3 test_deepseek_task_2.py
# python3 test_deepseek_task_2.py "What is Python?"

# Deactivate virtual environment
# deactivate

# Usage examples
# Basic question (default: Hello)
# python3 test_deepseek_task_2.py

# Custom question
# python3 test_deepseek_task_2.py "What is Python?"

# With max tokens and temperature (like test_deepseek.py)
# python3 test_deepseek_task_2.py "Tell me a short story" --max-tokens 500 --temperature 0.9

# More focused answer
# python3 test_deepseek_task_2.py "List 5 facts about Python" --temperature 0.3

# Explicit response format (added to system prompt)
# python3 test_deepseek_task_2.py "What is Docker?" --format "Answer in exactly 3 bullet points, each on a new line starting with -"

# Stop sequence — generation stops when this text appears
# (use --stop=VALUE if VALUE starts with "-", otherwise argparse treats it as another flag)
# python3 test_deepseek_task_2.py "Explain recursion briefly" --max-tokens 300 --stop=---END---

# Multiple stop sequences
# python3 test_deepseek_task_2.py "Write a haiku about code" --stop END --stop "###"

# Full control: format + length + temperature + stop
# python3 test_deepseek_task_2.py "What is Python?" \
#   --format 'JSON only: {"summary": string, "facts": [string, string, string]}' \
#   --max-tokens 200 \
#   --temperature 0.9 \
#   --stop=---END---
#######################################

import argparse
import os
import sys

from openai import OpenAI

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

parser = argparse.ArgumentParser(description="Ask questions to DeepSeek API (OpenAI SDK)")
parser.add_argument(
    "question",
    nargs="?",
    default="Hello",
    help="Your question for DeepSeek (default: Hello)",
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

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
)

request_kwargs = {
    "model": "deepseek-v4-flash",
    "messages": [
        {"role": "system", "content": system_content},
        {"role": "user", "content": args.question},
    ],
    "stream": False,
    "max_tokens": args.max_tokens,
    "temperature": args.temperature,
    "reasoning_effort": "high",
    "extra_body": {"thinking": {"type": "enabled"}},
}
if args.stop:
    request_kwargs["stop"] = args.stop

print(f"Q: {args.question}")
if args.format:
    print(f"Format: {args.format}")
print(f"max_tokens={args.max_tokens}, temperature={args.temperature}", end="")
if args.stop:
    print(f", stop={args.stop!r}", end="")
print("\n")
print("A: ", end="", flush=True)

response = client.chat.completions.create(**request_kwargs)

print(response.choices[0].message.content)

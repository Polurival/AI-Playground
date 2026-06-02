#!/usr/bin/env python3

#######################################
# Install venv if not already installed
# sudo apt install python3-venv

# Create a virtual environment
# python3 -m venv deepseek-env

# Activate it
# source deepseek-env/bin/activate

# Now pip works normally
# pip install requests

# Test your DeepSeek script
# python3 test_deepseek.py "What is Python?"

# Deactivate virtual environment
# deactivate

# Usage examples
# Basic question
# python3 test_deepseek.py "What is Python?"

# With custom max tokens
# python3 test_deepseek.py "Tell me a short story" --max-tokens 500

# With custom temperature (more creative)
# python3 test_deepseek.py "Write a poem about coding" --temperature 0.9

# More focused (less creative)
# python3 test_deepseek.py "List 5 facts about Python" --temperature 0.3

# Combine options
# python3 test_deepseek.py "Explain Docker" --max-tokens 300 --temperature 0.5
#######################################

import requests
import sys
import os
import argparse

# Get API key from environment variable
API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

# Set up command line argument parsing
parser = argparse.ArgumentParser(description='Ask questions to DeepSeek API')
parser.add_argument('question', type=str, help='Your question for DeepSeek')
parser.add_argument('--max-tokens', type=int, default=500, 
                    help='Maximum tokens in response (default: 500)')
parser.add_argument('--temperature', type=float, default=0.7,
                    help='Creativity level 0-1 (default: 0.7)')

args = parser.parse_args()

# API endpoint
url = "https://api.deepseek.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": args.question}
    ],
    "temperature": args.temperature,
    "max_tokens": args.max_tokens
}

print(f"Q: {args.question}\n")
print("A: ", end="", flush=True)

response = requests.post(url, json=payload, headers=headers)

if response.status_code == 200:
    result = response.json()
    answer = result["choices"][0]["message"]["content"]
    print(answer)
else:
    print(f"\nError: {response.status_code}")
    print(response.text)

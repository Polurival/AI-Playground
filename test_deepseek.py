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
# python3 test_deepseek.py

# Deactivate virtual environment
# deactivate
#######################################

import requests
import os

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    exit(1)

url = "https://api.deepseek.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": "What is Python used for? Give a short answer."}
    ],
    "temperature": 0.8,
    "max_tokens": 150
}

response = requests.post(url, json=payload, headers=headers)

if response.status_code == 200:
    result = response.json()
    print(result["choices"][0]["message"]["content"])
else:
    print(f"Error: {response.status_code}")
    print(response.text)

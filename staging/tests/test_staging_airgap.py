import os
import sys
import time
import requests

API_URL = os.getenv("API_URL", "http://localhost:8642/v1/chat/completions")
API_KEY = os.getenv("API_KEY", "hermes-api-secret")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/tags")

def test_airgapped_staging():
    print("🌟 Running Airgapped Staging Test Suite...")
    
    # 1. Test Ollama Health
    print("1. Checking Ollama gemma4 model availability...")
    try:
        r = requests.get(OLLAMA_URL, timeout=5)
        if r.status_code == 200:
            print("   ✅ Ollama service is online")
        else:
            print(f"   ❌ Ollama HTTP {r.status_code}")
    except Exception as e:
        print(f"   ❌ Ollama connection exception: {e}")

    # 2. Test Hermes API endpoint
    print("2. Querying Hermes API Server...")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "hermes-agent",
        "messages": [{"role": "user", "content": "Perform a pre-patch health check on rhel-prod-01"}],
        "stream": False
    }
    try:
        r = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            print("   ✅ Hermes API Query Response Received:")
            print("   " + r.json()['choices'][0]['message']['content'][:200] + "...")
        else:
            print(f"   ❌ Hermes API Error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"   ❌ Hermes API exception: {e}")

if __name__ == "__main__":
    test_airgapped_staging()

import requests
import json
import time

# Configuration from docker-compose.yml
BASE_URL = "http://localhost:8642"
API_KEY = "hermes-api-secret"
MODEL_NAME = "hermes-agent"  # Default if not specified

def test_health():
    print(f"Checking health endpoint: {BASE_URL}/health")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error connecting to health endpoint: {e}")
        return False

def test_models():
    print(f"\nChecking models endpoint: {BASE_URL}/v1/models")
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        response = requests.get(f"{BASE_URL}/v1/models", headers=headers, timeout=5)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            models = response.json()
            model_ids = [m['id'] for m in models.get('data', [])]
            print(f"Available models: {model_ids}")
            return MODEL_NAME in model_ids
        else:
            print(f"Error: {response.json()}")
            return False
    except Exception as e:
        print(f"Error connecting to models endpoint: {e}")
        return False

def test_chat_completion():
    print(f"\nTesting basic chat completion: {BASE_URL}/v1/chat/completions")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "Hello, who are you?"}],
        "stream": False
    }
    try:
        response = requests.post(f"{BASE_URL}/v1/chat/completions", headers=headers, json=payload, timeout=30)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message']['content']
            print(f"Response content: {content[:100]}...")
            return len(content) > 0
        else:
            print(f"Error: {response.json()}")
            return False
    except Exception as e:
        print(f"Error connecting to chat completions: {e}")
        return False

def test_ansible_tool_call():
    print(f"\nTesting Ansible Tool Call via API: {BASE_URL}/v1/chat/completions")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    # We ask a question that triggers the ansible_run_command tool
    # Using the explicit tool name to ensure the model knows what to use in this environment
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": "Run 'uptime' command on host 'test-server' using your ansible tools."}
        ],
        "stream": False
    }
    try:
        print("Sending request (waiting for agent reasoning and tool execution)...")
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/v1/chat/completions", headers=headers, json=payload, timeout=60)
        duration = time.time() - start_time
        print(f"Status: {response.status_code} (took {duration:.2f}s)")
        
        if response.status_code == 200:
            data = response.json()
            message = data['choices'][0]['message']
            content = message.get('content', '')
            
            print(f"Response content: {content[:300]}...")
            
            # Indicators of success:
            # 1. Mentioning "ansible" and "successful" or "completed"
            # 2. Or mentioning that it got a response from the AAP interface
            success_indicators = [
                "successful", "completed", "uptime", "ansible", "aap", "interface", "test-server"
            ]
            found_indicators = [i for i in success_indicators if i in content.lower()]
            
            if len(found_indicators) >= 2:
                print(f"✅ Success indicators found: {found_indicators}")
                return True
            else:
                print(f"❌ Response did not contain enough success indicators. Found: {found_indicators}")
                return False
        else:
            print(f"Error: {response.json()}")
            return False
    except Exception as e:
        print(f"Error connecting to chat completions: {e}")
        return False

if __name__ == "__main__":
    print("=== Hermes API Server Diagnostic Test ===")
    health_ok = test_health()
    models_ok = test_models()
    chat_ok = test_chat_completion()
    ansible_ok = test_ansible_tool_call()
    
    print("\n=== Summary ===")
    print(f"Health Endpoint: {'PASS' if health_ok else 'FAIL'}")
    print(f"Models Endpoint: {'PASS' if models_ok else 'FAIL'}")
    print(f"Chat Completion: {'PASS' if chat_ok else 'FAIL'}")
    print(f"Ansible Tool Call: {'PASS' if ansible_ok else 'FAIL'}")

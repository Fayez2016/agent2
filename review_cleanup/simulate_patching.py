import requests
import json
import time
import sys

# Configuration
API_URL = "http://localhost:8642/v1/chat/completions"
API_KEY = "hermes-api-secret"
MODEL = "hermes-agent"

# The fleet to patch (Mixed HA and Non-HA based on our mock data)
FLEET = [
    "rhel-prod-01.enterprise.local", # HA
    "rhel-prod-02.enterprise.local", # HA
    "rhel-app-01.enterprise.local",  # Non-HA, Planned Reboot
    "rhel-app-02.enterprise.local"   # Non-HA
]

def send_chat_command(command):
    print(f"📡 Sending command to Hermes: {command}")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": command}
        ],
        "stream": False # Set to False for easier response handling in simulation
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=600)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Error communicating with Hermes API: {e}")
        return None

def main():
    print("🚀 Starting Fleet Patching Simulation...")
    print(f"🎯 Target Fleet: {', '.join(FLEET)}")
    
    # Instruction to trigger the new skill
    prompt = (
        f"Use the 'fleet-patching-orchestrator' skill to patch the following fleet: {', '.join(FLEET)}. "
        "Please follow the SOP strictly, delegate tasks to subagents, handle reboots dynamically, "
        "and provide a final report via email when finished."
    )
    
    start_time = time.time()
    result = send_chat_command(prompt)
    
    if result:
        completion_text = result['choices'][0]['message']['content']
        print("\n" + "="*80)
        print("🤖 HERMES RESPONSE:")
        print("="*80)
        print(completion_text)
        print("="*80)
        
        duration = time.time() - start_time
        print(f"\n✅ Simulation completed in {duration:.2f} seconds.")
    else:
        print("\n❌ Simulation failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()

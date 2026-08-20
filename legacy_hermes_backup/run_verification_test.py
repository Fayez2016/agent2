import os
import sys
import time
import json
import requests
import threading
import subprocess
import re

HITL_URL = "http://localhost:5001"
API_URL = "http://localhost:8642/v1/chat/completions"
API_KEY = "hermes-api-secret"
HITL_PASSWORD = "admin123"

def print_header(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def step_1_check_containers():
    print_header("STEP 1: Checking Container Health")
    res = subprocess.run("podman ps --format '{{.Names}}\t{{.Status}}'", shell=True, capture_output=True, text=True)
    print(res.stdout)
    for expected in ["staging-hermes-agent", "staging-ansible-mcp", "staging-hitl-web", "staging-hitl-db", "staging-aap-server", "staging-ollama"]:
        if expected not in res.stdout:
            print(f"❌ Container {expected} is NOT running!")
            return False
    print("✅ All 6 required containers are UP and healthy.")
    return True

def step_2_hitl_approver_bot(stop_event, log_list):
    """Background thread to log in and approve pending HITL requests."""
    session = requests.Session()
    login_data = {"username": "admin", "password": HITL_PASSWORD}
    
    while not stop_event.is_set():
        try:
            resp = session.get(HITL_URL, timeout=5)
            if "Login" in resp.text and "Logout" not in resp.text:
                csrf_match = re.search(r'name="csrf_token" value="(.*?)"', resp.text)
                if csrf_match:
                    token = csrf_match.group(1)
                    login_resp = session.post(f"{HITL_URL}/login", data={**login_data, "csrf_token": token}, timeout=5, allow_redirects=True)
                    if login_resp.status_code == 200 and "Logout" in login_resp.text:
                        log_list.append("[HITL Bot] Logged into Web UI successfully.")
                        resp = login_resp
            
            if "Approve" in resp.text:
                forms = re.findall(r'action="/resolve/(\d+)".*?name="csrf_token" value="(.*?)"', resp.text, re.DOTALL)
                for request_id, csrf_token in forms:
                    log_list.append(f"[HITL Bot] Detected PENDING Request ID: {request_id}. Approving now...")
                    appr_resp = session.post(
                        f"{HITL_URL}/resolve/{request_id}",
                        data={"decision": "GRANTED", "csrf_token": csrf_token},
                        timeout=5
                    )
                    if appr_resp.status_code == 200:
                        log_list.append(f"[HITL Bot] Request {request_id} APPROVED (GRANTED) via Web Interface!")
        except Exception as e:
            log_list.append(f"[HITL Bot Error] {e}")
        
        time.sleep(2)

def step_3_run_end_to_end_test():
    print_header("STEP 2: Executing End-to-End High-Risk HITL Test")
    
    bot_logs = []
    stop_event = threading.Event()
    bot_thread = threading.Thread(target=step_2_hitl_approver_bot, args=(stop_event, bot_logs))
    bot_thread.start()
    
    query = "Put cluster node rhel-prod-01 in standby mode"
    print(f"Sending prompt to Hermes REST API: '{query}'")
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "hermes-agent",
        "messages": [{"role": "user", "content": query}],
        "stream": False
    }
    
    start_time = time.time()
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=600)
        elapsed = time.time() - start_time
        
        stop_event.set()
        bot_thread.join()
        
        print("\n--- HITL Bot Activity ---")
        for l in bot_logs:
            print(f"  {l}")
            
        print_header(f"STEP 3: REST API Response (Received in {elapsed:.2f}s)")
        if resp.status_code == 200:
            data = resp.json()
            content = data['choices'][0]['message']['content']
            print("Status Code: 200 OK")
            print("Response Content:")
            print(content)
        else:
            print(f"Status Code: {resp.status_code}")
            print(resp.text)
            
    except Exception as e:
        stop_event.set()
        bot_thread.join()
        print(f"❌ Request failed with error: {e}")
        return False

    print_header("STEP 4: Database Audit Log Verification")
    db_res = subprocess.run("podman exec staging-hitl-db psql -U postgres -d hitl -c 'SELECT id, action_name, action_summary, status, requested_at, resolved_at FROM hitl_requests ORDER BY id DESC LIMIT 5;'", shell=True, capture_output=True, text=True)
    print(db_res.stdout)
    
    print_header("STEP 5: AAP Server Job Launch Logs")
    aap_res = subprocess.run("podman logs --tail 15 staging-aap-server", shell=True, capture_output=True, text=True)
    print(aap_res.stdout)
    
    return True

if __name__ == "__main__":
    if not step_1_check_containers():
        sys.exit(1)
    step_3_run_end_to_end_test()

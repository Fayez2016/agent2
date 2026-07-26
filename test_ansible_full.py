import subprocess
import time
import os
import threading
import requests

# Configuration
AGENT_CONTAINER = "hermes-agent"
SERVER_CONTAINER = "aap-server"
HITL_URL = "http://localhost:5001"
LOG_FILE = "ansible_full_communication.log"
MODEL = "gemma4:31b"

# Full HA Lifecycle Test Cases
TEST_CASES = [
    {"name": "Pre-Patch Check", "query": "Perform a pre-patch cluster health check on the rhel-prod fleet"},
    {"name": "Maintenance Mode Enable", "query": "Enable global maintenance mode for the cluster"},
    {"name": "Node Isolation (Standby)", "query": "Put cluster node rhel-prod-01 in standby mode"},
    {"name": "Cluster Service Stop", "query": "Stop cluster services on rhel-prod-01"},
    {"name": "Fleet Patching", "query": "Apply security patches to the rhel-prod fleet"},
    {"name": "Node Reboot", "query": "Reboot the host rhel-prod-01"},
    {"name": "Package Installation", "query": "Install the 'httpd' package on rhel-prod-01"},
    {"name": "Filesystem Expansion", "query": "Expand the /var filesystem on rhel-prod-01"},
    {"name": "PCS Status Check", "query": "Get the basic PCS cluster status from rhel-prod-01"},
    {"name": "Fix PCS Cluster", "query": "Fix/Cleanup PCS cluster resources on rhel-prod-01"},
    {"name": "VMware Reset", "query": "Perform a hard reset on the VM 'rhel-prod-01' via VMware"},
    {"name": "Send Notification", "query": "Send a success email to admin@enterprise.local with subject 'Patching Complete' and body 'The fleet has been updated.'"},
    {"name": "Node Reintegration (Unstandby)", "query": "Take rhel-prod-01 out of standby mode and start cluster services"},
    {"name": "Maintenance Mode Disable", "query": "Disable global maintenance mode for the cluster"},
    {"name": "CIB Upgrade", "query": "Upgrade the cluster CIB to the latest version on rhel-prod-01"}
]

# API Configuration
API_URL = "http://localhost:8642/v1/chat/completions"
API_KEY = "hermes-api-secret"

def run_api_query(query):
    """Execute a query via the Hermes REST API listener."""
    print(f"Executing REST API Request: {API_URL}")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "hermes-agent",
        "messages": [{"role": "user", "content": query}],
        "stream": False
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=300)
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content']
        else:
            return f"API Error: {resp.status_code} - {resp.text}"
    except Exception as e:
        return f"API Exception: {str(e)}"

def hitl_auto_approver():
    """Background thread to automatically approve HITL requests via the authenticated web interface."""
    print("[HITL Bot] Started auto-approver thread...")
    session = requests.Session()
    login_data = {"username": "admin", "password": "admin123"}
    
    is_logged_in = False

    while getattr(threading.current_thread(), "do_run", True):
        try:
            # Check the current status
            resp = session.get(HITL_URL, timeout=5)
            
            # 1. Determine if we need to log in
            needs_login = "Login" in resp.text and "Logout" not in resp.text
            
            if needs_login:
                print("[HITL Bot] Authentication required. Logging in...")
                csrf_match = re.search(r'name="csrf_token" value="(.*?)"', resp.text)
                if csrf_match:
                    token = csrf_match.group(1)
                    login_payload = {**login_data, "csrf_token": token}
                    login_resp = session.post(f"{HITL_URL}/login", data=login_payload, timeout=5, allow_redirects=True)
                    if login_resp.status_code == 200 and "Logout" in login_resp.text:
                        print("[HITL Bot] Successfully logged in.")
                        is_logged_in = True
                        resp = login_resp
                    else:
                        print(f"[HITL Bot] Login failed with status {login_resp.status_code}. Retrying...")
                        time.sleep(5)
                        continue
                else:
                    print("[HITL Bot] CRITICAL: Could not find CSRF token on login page.")
                    time.sleep(5)
                    continue

            # 2. Process pending approvals
            if "Approve" in resp.text:
                forms = re.findall(r'action="/resolve/(\d+)".*?name="csrf_token" value="(.*?)"', resp.text, re.DOTALL)
                
                if not forms:
                    print("[HITL Bot] Found 'Approve' text but no valid resolve forms/tokens.")
                
                for request_id, csrf_token in forms:
                    print(f"\n[HITL Bot] Pending request {request_id} detected! Sending APPROVAL...")
                    appr_resp = session.post(
                        f"{HITL_URL}/resolve/{request_id}", 
                        data={"decision": "GRANTED", "csrf_token": csrf_token}, 
                        timeout=5
                    )
                    if appr_resp.status_code == 200:
                        print(f"[HITL Bot] Request {request_id} approved successfully.")
                    else:
                        print(f"[HITL Bot] Approval failed for {request_id} (Status: {appr_resp.status_code})")
        
        except Exception as e:
            print(f"[HITL Bot] Runtime Error: {e}")
        
        time.sleep(5)


import re

def run_cmd(cmd):
    print(f"Executing: {cmd}")
    # Using a longer timeout for individual agent turns
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    return result.stdout + result.stderr

def log(header, content):
    with open(LOG_FILE, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f" {header} \n")
        f.write(f"{'='*80}\n")
        f.write(content)
        f.write("\n")

def main():
    # Clear previous log
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    print(f"Starting End-to-End HA Patching Test.")
    print(f"Monitor the HITL Gate manually at: {HITL_URL}")
    print(f"Results will be streamed to: {LOG_FILE}")
    
    # Start HITL Approver
    t = threading.Thread(target=hitl_auto_approver)
    t.do_run = True
    t.start()

    try:
        log("E2E TEST START", f"Timestamp: {time.ctime()}\nModel: {MODEL}")

        for i, case in enumerate(TEST_CASES, 1):
            print(f"\n--- [Step {i}/{len(TEST_CASES)}] Testing: {case['name']} ---")
            
            start_time = time.time()
            # Alternate between CLI and REST API to test both listeners
            if i % 2 == 0:
                agent_output = run_api_query(case['query'])
            else:
                # Using the absolute path for hermes to avoid PATH issues
                query_cmd = f"podman exec -u hermes {AGENT_CONTAINER} /opt/hermes/.venv/bin/python /opt/hermes/.venv/bin/hermes chat -q '{case['query']}' -m {MODEL} -v"
                agent_output = run_cmd(query_cmd)
            
            duration = time.time() - start_time
            
            # Log interaction
            log(f"STEP {i}: {case['name']}\nQUERY: {case['query']}\nDURATION: {duration:.2f}s", agent_output)
            
            # Capture AAP Server logs
            server_logs = run_cmd(f"podman logs --tail 30 {SERVER_CONTAINER}")
            log(f"SERVER LOGS: {case['name']}", server_logs)
            
            print(f"--- [Step {i}] Completed in {duration:.2f}s ---")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
    finally:
        t.do_run = False
        t.join()

    print(f"\nFull E2E test complete. Communication log: {os.path.abspath(LOG_FILE)}")

if __name__ == "__main__":
    main()

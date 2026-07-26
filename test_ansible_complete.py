import subprocess
import time
import os
import threading
import requests
import re
import sys

# Configuration
AGENT_CONTAINER = "hermes-agent"
SERVER_CONTAINER = "aap-server"
HITL_URL = "http://localhost:5001"
LOG_FILE = "ansible_complete_test.log"
API_URL = "http://localhost:8642/v1/chat/completions"
API_KEY = os.getenv("API_SERVER_KEY", "hermes-api-secret") # Fallback for local testing if env not sourced
HITL_PASSWORD = os.getenv("HITL_PASSWORD", "admin123")

# Test Phases
# Phase 1: Individual Tool/Command Testing (Low-level validation)
INDIVIDUAL_TESTS = [
    {"name": "Pre-Patch Check", "query": "Perform a pre-patch cluster health check on the rhel-prod fleet"},
    {"name": "Maintenance Mode Enable", "query": "Enable global maintenance mode for the cluster"},
    {"name": "Node Isolation (Standby)", "query": "Put cluster node rhel-prod-01 in standby mode"},
    {"name": "Cluster Service Stop", "query": "Stop cluster services on rhel-prod-01"},
    {"name": "Individual Patching", "query": "Apply security patches to the rhel-prod-01 host only"},
    {"name": "Node Reboot", "query": "Reboot the host rhel-prod-01"},
    {"name": "Package Installation", "query": "Install the 'httpd' package on rhel-prod-01"},
    {"name": "Filesystem Expansion", "query": "Expand the /var filesystem on rhel-prod-01"},
    {"name": "PCS Status Check", "query": "Get the basic PCS cluster status from rhel-prod-01"},
    {"name": "Fix PCS Cluster", "query": "Fix/Cleanup PCS cluster resources on rhel-prod-01"},
    {"name": "VMware Reset", "query": "Perform a hard reset on the VM 'rhel-prod-01' via VMware"},
    {"name": "Send Notification", "query": "Send a success email to admin@enterprise.local with subject 'Tool Test' and body 'Testing individual tools.'"},
    {"name": "Node Reintegration (Unstandby)", "query": "Take rhel-prod-01 out of standby mode and start cluster services"},
    {"name": "Maintenance Mode Disable", "query": "Disable global maintenance mode for the cluster"}
]

# Phase 2: Full Fleet Patching Orchestration Simulation (High-level orchestration)
FLEET = [
    "rhel-prod-01.enterprise.local", # HA
    "rhel-prod-02.enterprise.local", # HA
    "rhel-app-01.enterprise.local",  # Non-HA, Planned Reboot
    "rhel-app-02.enterprise.local"   # Non-HA
]

ORCHESTRATION_QUERY = (
    f"Use the 'fleet-patching-orchestrator' skill to patch the following fleet: {', '.join(FLEET)}. "
    "Please follow the SOP strictly, delegate tasks to subagents, handle reboots dynamically, "
    "and provide a final report via email when finished."
)

def run_api_query(query):
    """Execute a query via the Hermes REST API listener."""
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
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=600)
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
    login_data = {"username": "admin", "password": HITL_PASSWORD}
    
    is_logged_in = False

    while getattr(threading.current_thread(), "do_run", True):
        try:
            # Check the current status
            resp = session.get(HITL_URL, timeout=5)
            
            # 1. Determine if we need to log in
            # We need to log in if "Login" is present but "Logout" is NOT present
            needs_login = "Login" in resp.text and "Logout" not in resp.text
            
            if needs_login:
                print("[HITL Bot] Authentication required. Logging in...")
                csrf_match = re.search(r'name="csrf_token" value="(.*?)"', resp.text)
                if csrf_match:
                    token = csrf_match.group(1)
                    login_payload = {**login_data, "csrf_token": token}
                    # Post to login and follow redirects to ensure we land on a valid page
                    login_resp = session.post(f"{HITL_URL}/login", data=login_payload, timeout=5, allow_redirects=True)
                    if login_resp.status_code == 200 and "Logout" in login_resp.text:
                        print("[HITL Bot] Successfully logged in.")
                        is_logged_in = True
                        resp = login_resp # Use the new response (the dashboard)
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
                # Find all resolve forms. Regex captures request_id and the unique CSRF token for that form.
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
        
        time.sleep(5) # Slow down polling to be kind to the server and logs

def log(header, content):
    with open(LOG_FILE, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f" {header} \n")
        f.write(f"{'='*80}\n")
        f.write(content)
        f.write("\n")

def main():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    print("🌟 Starting Complete Ansible & Orchestration Test Suite")
    print(f"📄 Detailed logs: {os.path.abspath(LOG_FILE)}")
    
    t = threading.Thread(target=hitl_auto_approver)
    t.do_run = True
    t.start()

    try:
        # Phase 1: Tool Tests
        print("\n🚀 PHASE 1: TESTING INDIVIDUAL TOOLS")
        for i, case in enumerate(INDIVIDUAL_TESTS, 1):
            print(f"  [{i}/{len(INDIVIDUAL_TESTS)}] {case['name']}...", end="", flush=True)
            start_time = time.time()
            output = run_api_query(case['query'])
            duration = time.time() - start_time
            log(f"INDIVIDUAL TOOL TEST: {case['name']}", f"QUERY: {case['query']}\nDURATION: {duration:.2f}s\n\n{output}")
            print(f" Done ({duration:.2f}s)")

        # Phase 2: Orchestration Simulation
        print("\n🚀 PHASE 2: FULL FLEET ORCHESTRATION SIMULATION")
        print(f"  Executing Skill: fleet-patching-orchestrator...", end="", flush=True)
        start_time = time.time()
        orchestration_output = run_api_query(ORCHESTRATION_QUERY)
        duration = time.time() - start_time
        log("FULL ORCHESTRATION SIMULATION", f"QUERY: {ORCHESTRATION_QUERY}\nDURATION: {duration:.2f}s\n\n{orchestration_output}")
        print(f" Done ({duration:.2f}s)")

        print("\n" + "="*80)
        print("🤖 ORCHESTRATION SUMMARY OUTPUT:")
        print("="*80)
        print(orchestration_output)
        print("="*80)

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
    finally:
        t.do_run = False
        t.join()

    print(f"\n✅ All tests complete. See {LOG_FILE} for full details.")

if __name__ == "__main__":
    main()

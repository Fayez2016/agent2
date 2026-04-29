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
MODEL = "qwen3-coder-next"

# Full HA Lifecycle Test Cases
TEST_CASES = [
    {"name": "Pre-Patch Check", "query": "Perform a pre-patch cluster health check on the rhel-prod fleet"},
    {"name": "Maintenance Mode Enable", "query": "Enable global maintenance mode for the cluster"},
    {"name": "Node Isolation (Standby)", "query": "Put cluster node rhel-prod-01 in standby mode"},
    {"name": "Cluster Service Stop", "query": "Stop cluster services on rhel-prod-01"},
    {"name": "Fleet Patching", "query": "Apply security patches to the rhel-prod fleet"},
    {"name": "Node Reboot", "query": "Reboot the host rhel-prod-01"},
    {"name": "Node Reintegration (Unstandby)", "query": "Take rhel-prod-01 out of standby mode and start cluster services"},
    {"name": "Maintenance Mode Disable", "query": "Disable global maintenance mode for the cluster"},
    {"name": "CIB Upgrade", "query": "Upgrade the cluster CIB to the latest version on rhel-prod-01"}
]

def hitl_auto_approver():
    """Background thread to automatically approve HITL requests."""
    print("[HITL Bot] Started auto-approver thread...")
    while getattr(threading.current_thread(), "do_run", True):
        try:
            # Check for Pending status in HTML
            resp = requests.get(HITL_URL, timeout=5)
            if "PENDING" in resp.text or "authorization" in resp.text:
                print(f"\n[HITL Bot] Pending request detected! Body contains: ...{resp.text[200:400]}...")
                print(f"[HITL Bot] Sending APPROVAL (decision=GRANTED) to {HITL_URL}/resolve...")
                post_resp = requests.post(f"{HITL_URL}/resolve", data={"decision": "GRANTED"}, timeout=5)
                if post_resp.status_code == 200:
                    print("[HITL Bot] ✅ Approval successfully recorded.")
                else:
                    print(f"[HITL Bot] ❌ Failed to record approval. Status: {post_resp.status_code}")
        except Exception as e:
            # Silently retry on connection errors during container startup
            pass
        time.sleep(2)

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
            
            # Using the absolute path for hermes to avoid PATH issues
            query_cmd = f"podman exec -u hermes {AGENT_CONTAINER} /opt/hermes/.venv/bin/python /opt/hermes/.venv/bin/hermes chat -q '{case['query']}' -m {MODEL} -v"
            
            start_time = time.time()
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

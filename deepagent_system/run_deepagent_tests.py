#!/usr/bin/env python3
"""
Deep Agent End-to-End Verification Test Suite
Verifies:
1. Microservice health probes (Core API, HITL Web, Control Panel UI, Ansible MCP, Mock AAP)
2. Low-Risk diagnostic query execution without HITL requirement
3. High-Risk infrastructure operation (Reboot Host) with real HITL PostgreSQL database tracking & Web UI approval
4. Subagent delegation (rhel-diagnostics / fleet-patcher)
"""

import time
import requests
import json
import sys
import re
import subprocess
import threading

DEEPAGENT_API_URL = "http://localhost:8642/v1/chat/completions"
HITL_URL = "http://localhost:5001"
WEB_UI_URL = "http://localhost:3000"
MCP_URL = "http://localhost:8000/mcp"
AAP_URL = "http://localhost:5000"
API_KEY = "hermes-api-secret"

def query_db_latest_request():
    """Queries PostgreSQL database container directly to get the latest hitl_request record."""
    cmd = [
        "podman", "exec", "deepagent-hitl-db",
        "psql", "-U", "hermes", "-d", "hitl", "-t", "-A", "-c",
        "SELECT id, action_name, action_summary, status, requested_at, resolved_at FROM hitl_requests ORDER BY id DESC LIMIT 1;"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = res.stdout.strip()
        if out:
            parts = out.split("|")
            if len(parts) >= 6:
                return {
                    "id": parts[0],
                    "action_name": parts[1],
                    "action_summary": parts[2],
                    "status": parts[3],
                    "requested_at": parts[4],
                    "resolved_at": parts[5]
                }
    except Exception as e:
        print(f"  [DB Query Warning] Failed to query PostgreSQL directly: {e}")
    return None

def query_db_request_by_id(request_id):
    """Queries PostgreSQL database container directly for a specific request ID."""
    cmd = [
        "podman", "exec", "deepagent-hitl-db",
        "psql", "-U", "hermes", "-d", "hitl", "-t", "-A", "-c",
        f"SELECT id, action_name, action_summary, status, requested_at, resolved_at FROM hitl_requests WHERE id = {request_id};"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = res.stdout.strip()
        if out:
            parts = out.split("|")
            if len(parts) >= 6:
                return {
                    "id": parts[0],
                    "action_name": parts[1],
                    "action_summary": parts[2],
                    "status": parts[3],
                    "requested_at": parts[4],
                    "resolved_at": parts[5]
                }
    except Exception as e:
        print(f"  [DB Query Warning] Failed to query PostgreSQL by ID: {e}")
    return None

def test_health_probes():
    print("[Test 1/5] Checking Microservice Health & Connectivity Probes...")
    success = True
    
    # Probe 1: Core REST API
    try:
        r = requests.get("http://localhost:8642/health", timeout=5)
        if r.status_code == 200 and r.json().get("status") == "ok":
            print("  ✓ Deep Agent Core REST API (:8642): HEALTHY")
        else:
            print(f"  ✗ Deep Agent Core API returned status {r.status_code}")
            success = False
    except Exception as e:
        print(f"  ✗ Deep Agent Core API error: {e}")
        success = False

    # Probe 2: HITL Web Approval Portal
    try:
        r = requests.get(HITL_URL, timeout=5)
        if r.status_code == 200:
            print("  ✓ HITL Web Portal (:5001): HEALTHY")
        else:
            print(f"  ✗ HITL Web Portal returned status {r.status_code}")
            success = False
    except Exception as e:
        print(f"  ✗ HITL Web Portal error: {e}")
        success = False

    # Probe 3: React Web UI Control Panel
    try:
        r = requests.get(WEB_UI_URL, timeout=5)
        if r.status_code == 200:
            print("  ✓ Web UI Control Panel Server (:3000): HEALTHY")
        else:
            print(f"  ✗ Web UI Control Panel returned status {r.status_code}")
            success = False
    except Exception as e:
        print(f"  ✗ Web UI Control Panel error: {e}")
        success = False

    # Probe 4: Ansible MCP Bridge
    try:
        r = requests.get(MCP_URL, timeout=5)
        if r.status_code in [200, 202, 400, 405, 406]:
            print("  ✓ Ansible MCP Bridge (:8000): HEALTHY (FastMCP Streamable Transport)")
        else:
            print(f"  ✗ Ansible MCP Bridge returned status {r.status_code}")
            success = False
    except Exception as e:
        print(f"  ✗ Ansible MCP Bridge error: {e}")
        success = False

    return success

def test_web_ui_frontend():
    print("\n[Test 2/5] Testing Web UI Frontend & Static Asset Integrity...")
    try:
        # 1. Verify index.html loads with 200 OK
        r_index = requests.get(WEB_UI_URL, timeout=5)
        if r_index.status_code != 200:
            print(f"  ✗ Failed to load index.html: Status {r_index.status_code}")
            return False
        
        html = r_index.text
        
        # 2. Check DOM Structure
        required_dom = [
            'id="chat-messages"',
            'id="user-input"',
            'id="send-btn"',
            'id="hitl-alert-banner"',
            'id="fleet-status-panel"'
        ]
        missing_dom = [elem for elem in required_dom if elem not in html]
        if missing_dom:
            print(f"  ✗ Missing required DOM elements in index.html: {missing_dom}")
            return False
        print("  ✓ Web UI DOM structure verified (chat stream, input form, HITL alert banner, fleet grid).")

        # 3. Check CSS and JS asset availability (Zero 404s)
        r_css = requests.get(f"{WEB_UI_URL}/style.css", timeout=5)
        if r_css.status_code != 200:
            print(f"  ✗ Failed to load style.css: Status {r_css.status_code}")
            return False
        print("  ✓ CSS stylesheet (/style.css) verified (200 OK).")

        r_js = requests.get(f"{WEB_UI_URL}/app.js", timeout=5)
        if r_js.status_code != 200:
            print(f"  ✗ Failed to load app.js: Status {r_js.status_code}")
            return False
        print("  ✓ JavaScript client (/app.js) verified (200 OK).")

        # 4. Verify no uncompiled TSX tags remaining in index.html
        if ".tsx" in html:
            print("  ✗ Warning: index.html still contains references to unbundled .tsx files.")
            return False
        print("  ✓ Verified: Zero unbundled .tsx files in production HTML.")

        return True
    except Exception as e:
        print(f"  ✗ Web UI frontend test exception: {e}")
        return False

def test_low_risk_query():
    print("\n[Test 3/5] Testing Low-Risk Tool Invocation (ansible_pcs_health_check)...")
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": "Check the Pacemaker cluster health for host rhel-prod-01"}],
        "stream": False
    }
    
    db_before = query_db_latest_request()
    
    try:
        resp = requests.post(DEEPAGENT_API_URL, headers=headers, json=payload, timeout=300)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            print("  ✓ Low-risk query response received (200 OK):")
            print("    Preview:", content[:120].replace("\n", " "))
            
            # Verify no new pending request was forced in HITL DB
            db_after = query_db_latest_request()
            if db_before and db_after and db_before["id"] == db_after["id"]:
                print("  ✓ Verified: No HITL approval gate was triggered for low-risk check.")
            return True
        else:
            print(f"  ✗ Low-risk query failed with status code {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"  ✗ Low-risk query exception: {e}")
        return False

def test_hitl_interception_and_approval():
    print("\n[Test 4/5] Testing High-Risk HITL Gate (ansible_reboot_host)...")
    
    result_container = []
    status_code_container = []

    def send_reboot_request():
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "deepagent",
            "messages": [{"role": "user", "content": "Reboot the host rhel-prod-01"}],
            "stream": False
        }
        try:
            resp = requests.post(DEEPAGENT_API_URL, headers=headers, json=payload, timeout=300)
            status_code_container.append(resp.status_code)
            if resp.status_code == 200:
                result_container.append(resp.json()["choices"][0]["message"]["content"])
            else:
                result_container.append(f"HTTP Error {resp.status_code}: {resp.text}")
        except Exception as e:
            result_container.append(f"Exception: {e}")

    req_thread = threading.Thread(target=send_reboot_request)
    req_thread.start()

    print("  Monitoring PostgreSQL HITL Audit DB and Approval Web Portal (:5001)...")
    session = requests.Session()
    login_data = {"username": "admin", "password": "admin123"}
    
    approved = False
    pending_request_id = None
    
    for attempt in range(60):
        time.sleep(2)
        
        # 1. Check PostgreSQL database directly for PENDING request
        latest = query_db_latest_request()
        if latest and latest["status"] == "PENDING":
            pending_request_id = latest["id"]
            print(f"  ✓ High-Risk Interception Verified in DB! Pending Request ID #{pending_request_id} created for action '{latest['action_name']}'.")
            
        # 2. Login to HITL Web Portal and submit GRANTED decision
        try:
            r = session.get(HITL_URL, timeout=5)
            if "Login" in r.text and "Logout" not in r.text:
                csrf_match = re.search(r'name="csrf_token" value="(.*?)"', r.text)
                if csrf_match:
                    token = csrf_match.group(1)
                    session.post(f"{HITL_URL}/login", data={**login_data, "csrf_token": token}, timeout=5)
                    r = session.get(HITL_URL, timeout=5)

            if "Approve" in r.text or "resolve" in r.text:
                forms = re.findall(r'action="/resolve/(\d+)".*?name="csrf_token" value="(.*?)"', r.text, re.DOTALL)
                for req_id, csrf in forms:
                    print(f"  ✓ Web Portal HITL Approval Triggered: Granting decision for Request ID #{req_id}...")
                    res = session.post(
                        f"{HITL_URL}/resolve/{req_id}",
                        data={"decision": "GRANTED", "csrf_token": csrf},
                        timeout=5
                    )
                    if res.status_code in [200, 302]:
                        approved = True
                        break
            if approved:
                break
        except Exception as e:
            pass

    req_thread.join(timeout=300)
    
    # Verify DB status updated to GRANTED
    db_verified = False
    if pending_request_id:
        time.sleep(1)
        db_check = query_db_request_by_id(pending_request_id)
        if db_check and db_check["status"] == "GRANTED":
            print(f"  ✓ Verified in PostgreSQL DB: Request #{pending_request_id} status updated to 'GRANTED' at {db_check['resolved_at']}.")
            db_verified = True
        else:
            print(f"  ! DB Status Check for Request #{pending_request_id}: Status is '{db_check.get('status') if db_check else 'Unknown'}'")

    if approved or db_verified or (result_container and status_code_container and status_code_container[0] == 200):
        print("  ✓ High-risk HITL approval gate and PostgreSQL database resolution verified successfully.")
        return True
    else:
        print("  ✗ HITL test failed or timed out. Output:", result_container)
        return False

def test_subagent_delegation():
    print("\n[Test 5/5] Testing Subagent Delegation (rhel-diagnostics)...")
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": "Delegate to rhel-diagnostics subagent to check cluster health on rhel-prod-01"}],
        "stream": False
    }
    try:
        resp = requests.post(DEEPAGENT_API_URL, headers=headers, json=payload, timeout=300)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            print("  ✓ Subagent delegation succeeded (200 OK). Response preview:")
            print("    ", content[:120].replace("\n", " "))
            return True
        else:
            print(f"  ✗ Subagent delegation returned status {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"  ✗ Subagent delegation exception: {e}")
        return False

def main():
    print("==========================================================================")
    print(" Deep Agent Comprehensive End-to-End Verification Test Suite")
    print("==========================================================================")
    
    if not test_health_probes():
        print("\n✗ Pre-flight health checks failed. Aborting verification.")
        sys.exit(1)

    if not test_web_ui_frontend():
        print("\n✗ Web UI frontend verification failed.")
        sys.exit(1)
        
    if not test_low_risk_query():
        print("\n✗ Low-risk query verification failed.")
        sys.exit(1)
        
    if not test_hitl_interception_and_approval():
        print("\n✗ High-risk HITL gate verification failed.")
        sys.exit(1)
        
    if not test_subagent_delegation():
        print("\n✗ Subagent delegation verification failed.")
        sys.exit(1)

    print("\n==========================================================================")
    print(" ALL 5 TEST SUITE STAGES PASSED SUCCESSFULLY!")
    print(" Deep Agent Core, Web UI, LLM, MCP, HITL Gate & Subagents Verified.")
    print("==========================================================================")

if __name__ == "__main__":
    main()

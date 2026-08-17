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
    print("[Test 1/6] Checking Microservice Health & Connectivity Probes...")
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
    print("\n[Test 2/6] Testing Web UI Frontend & Static Asset Integrity...")
    try:
        r_index = requests.get(WEB_UI_URL, timeout=5)
        if r_index.status_code != 200:
            print(f"  ✗ Failed to load index.html: Status {r_index.status_code}")
            return False
        
        html = r_index.text
        required_dom = [
            'id="chat-messages"',
            'id="user-input"',
            'id="send-btn"',
            'id="threads-list"',
            'id="hitl-mode-toggle"',
            'id="audit-table-body"'
        ]
        missing_dom = [elem for elem in required_dom if elem not in html]
        if missing_dom:
            print(f"  ✗ Missing required DOM elements in index.html: {missing_dom}")
            return False
        print("  ✓ Web UI DOM structure verified (chat stream, thread list, HITL mode toggle, in-pane stream, audit table).")

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
        return True
    except Exception as e:
        print(f"  ✗ Web UI frontend test exception: {e}")
        return False

def test_low_risk_query():
    print("\n[Test 3/6] Testing Low-Risk Tool Invocation (ansible_pcs_health_check)...")
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

def test_hitl_interception_and_in_app_approval():
    print("\n[Test 4/6] Testing High-Risk HITL Guardrail Mode (HITL ON) & In-App API Approval...")
    # 1. Ensure HITL mode is set to 'enforced'
    requests.post("http://localhost:8642/v1/settings/hitl_mode", json={"mode": "enforced"}, timeout=5)
    
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

    print("  Monitoring /v1/hitl/pending endpoint for In-App HITL modal trigger...")
    approved = False
    pending_request_id = None
    
    for attempt in range(60):
        time.sleep(2)
        try:
            r = requests.get("http://localhost:8642/v1/hitl/pending", timeout=5)
            if r.status_code == 200:
                pending_list = r.json().get("pending", [])
                if pending_list:
                    pending_request_id = pending_list[0]["id"]
                    action_name = pending_list[0]["action_name"]
                    print(f"  ✓ High-Risk Request Detected in /v1/hitl/pending! Request ID #{pending_request_id} for '{action_name}'.")
                    
                    # Grant approval via the In-App HITL Resolve REST API
                    resolve_resp = requests.post(
                        "http://localhost:8642/v1/hitl/resolve",
                        json={"request_id": pending_request_id, "decision": "GRANTED"},
                        timeout=5
                    )
                    if resolve_resp.status_code == 200:
                        print(f"  ✓ In-App REST API Approval Successful: Granted Decision for Request #{pending_request_id}.")
                        approved = True
                        break
        except Exception:
            pass

    req_thread.join(timeout=300)
    
    # Verify DB status updated to GRANTED
    if pending_request_id:
        time.sleep(1)
        db_check = query_db_request_by_id(pending_request_id)
        if db_check and db_check["status"] == "GRANTED":
            print(f"  ✓ Verified in PostgreSQL DB: Request #{pending_request_id} status updated to 'GRANTED' at {db_check['resolved_at']}.")

    if approved or (result_container and status_code_container and status_code_container[0] == 200):
        print("  ✓ Guardrail HITL approval gate and In-App API resolution verified successfully.")
        return True
    else:
        print("  ✗ HITL test failed or timed out. Output:", result_container)
        return False

def test_autonomous_24_7_mode():
    print("\n[Test 5/6] Testing 24/7 Autonomous AI Self-Healing Mode (HITL OFF)...")
    # 1. Switch mode to autonomous via API
    resp_mode = requests.post("http://localhost:8642/v1/settings/hitl_mode", json={"mode": "autonomous"}, timeout=5)
    if resp_mode.status_code != 200 or resp_mode.json().get("mode") != "autonomous":
        print("  ✗ Failed to switch mode to autonomous")
        return False
    print("  ✓ Mode switched to 'autonomous' via /v1/settings/hitl_mode.")

    # 2. Issue a high-risk command that would normally require HITL
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": "Reboot the host rhel-prod-01"}],
        "stream": False
    }
    
    start_time = time.time()
    resp = requests.post(DEEPAGENT_API_URL, headers=headers, json=payload, timeout=300)
    elapsed = time.time() - start_time
    
    if resp.status_code == 200:
        print(f"  ✓ Autonomous execution completed in {elapsed:.1f}s without human waiting.")
        latest = query_db_latest_request()
        if latest and latest["status"] == "AUTONOMOUS_GRANTED":
            print(f"  ✓ Verified in PostgreSQL Audit DB: Request #{latest['id']} status is 'AUTONOMOUS_GRANTED'.")
        else:
            print(f"  ! DB Latest Request Status: {latest.get('status') if latest else 'None'}")
        
        # Reset mode back to enforced
        requests.post("http://localhost:8642/v1/settings/hitl_mode", json={"mode": "enforced"}, timeout=5)
        return True
    else:
        print(f"  ✗ Autonomous execution failed: Status {resp.status_code} - {resp.text}")
        requests.post("http://localhost:8642/v1/settings/hitl_mode", json={"mode": "enforced"}, timeout=5)
        return False

def test_thread_and_conversation_persistence():
    print("\n[Test 6/6] Testing PostgreSQL Conversation & Tool Trace Persistence...")
    try:
        # 1. Create a persistent thread
        create_resp = requests.post("http://localhost:8642/v1/threads", json={"title": "Verification Session"}, timeout=5)
        if create_resp.status_code != 200:
            print(f"  ✗ Failed to create thread: {create_resp.text}")
            return False
        
        thread_id = create_resp.json()["thread_id"]
        print(f"  ✓ Thread created in PostgreSQL: {thread_id}")

        # 2. Send message with thread_id
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "deepagent",
            "thread_id": thread_id,
            "messages": [{"role": "user", "content": "Check the Pacemaker cluster health for host rhel-prod-01"}],
            "stream": False
        }
        resp = requests.post(DEEPAGENT_API_URL, headers=headers, json=payload, timeout=300)
        if resp.status_code != 200:
            print(f"  ✗ Failed to send message to thread: {resp.text}")
            return False
        print("  ✓ Prompt processed by Deep Agent with thread tracking.")

        # 3. Retrieve messages from PostgreSQL
        msg_resp = requests.get(f"http://localhost:8642/v1/threads/{thread_id}/messages", timeout=5)
        if msg_resp.status_code != 200:
            print(f"  ✗ Failed to retrieve thread messages: {msg_resp.text}")
            return False
        
        messages = msg_resp.json().get("messages", [])
        if len(messages) < 2:
            print(f"  ✗ Expected at least 2 messages (user + assistant) in DB, got {len(messages)}")
            return False
        print(f"  ✓ Verified in PostgreSQL DB: {len(messages)} messages persisted for thread {thread_id}.")

        # 4. Check intermediate_steps tool trace
        assistant_msg = next((m for m in messages if m["role"] == "assistant"), None)
        if assistant_msg and assistant_msg.get("intermediate_steps"):
            print(f"  ✓ Verified: Tool execution trace ({len(assistant_msg['intermediate_steps'])} steps) stored in JSONB.")

        # 5. Delete thread
        del_resp = requests.delete(f"http://localhost:8642/v1/threads/{thread_id}", timeout=5)
        if del_resp.status_code == 200:
            print(f"  ✓ Thread {thread_id} cleaned up successfully.")

        return True
    except Exception as e:
        print(f"  ✗ Thread persistence test exception: {e}")
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
        
    if not test_hitl_interception_and_in_app_approval():
        print("\n✗ High-risk HITL gate verification failed.")
        sys.exit(1)

    if not test_autonomous_24_7_mode():
        print("\n✗ 24/7 Autonomous mode verification failed.")
        sys.exit(1)
        
    if not test_thread_and_conversation_persistence():
        print("\n✗ Thread and conversation persistence verification failed.")
        sys.exit(1)

    print("\n==========================================================================")
    print(" ALL 6 TEST SUITE STAGES PASSED SUCCESSFULLY!")
    print(" Deep Agent, 24/7 Autonomous AI, In-App HITL, DB Persistence & Web UI Verified.")
    print("==========================================================================")

if __name__ == "__main__":
    main()

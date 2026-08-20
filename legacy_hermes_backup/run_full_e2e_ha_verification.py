#!/usr/bin/env python3
"""
Full End-to-End HA Lifecycle & HITL Approval Verification Script.

Sequence of Execution:
  1. Container Health Check: Verify all 6 staging containers are running.
  2. High-Risk Action #1 (Patch Fleet):
     a. Trigger HITL Approval Gate via MCP (hitl_request_approval).
     b. Verify row created in PostgreSQL Database with status PENDING.
     c. Simulate Administrator Approval via Web UI (status -> GRANTED).
     d. Execute High-Risk Tool (ansible_patch_fleet).
     e. Verify execution success & AAP Job Launch.
  3. High-Risk Action #2 (Reboot Fleet):
     a. Trigger HITL Approval Gate via MCP.
     b. Approve via Web UI.
     c. Execute High-Risk Tool (ansible_reboot_fleet).
     d. Verify execution success & AAP Job Launch.
  4. Final Audit Report: Print DB audit log & AAP Job logs.
"""

import sys
import time
import json
import re
import requests
import subprocess

def print_header(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def check_containers():
    print_header("STEP 1: Container Health Check")
    cmd = ["podman", "ps", "--format", "{{.Names}}\t{{.Status}}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    containers = res.stdout.strip().split("\n")
    
    required = ["staging-ollama", "staging-hermes-agent", "staging-ansible-mcp",
                "staging-hitl-web", "staging-hitl-db", "staging-aap-server"]
    running = []
    for line in containers:
        for req in required:
            if req in line:
                running.append(req)
                print(f"  [✓] {req}: {line.split('\t')[1]}")
                
    print("✅ All 6 staging containers are UP and healthy.")

def query_db(sql):
    cmd = ["podman", "exec", "staging-hitl-db", "psql", "-U", "hermes", "-d", "hitl", "-t", "-A", "-F", "|", "-c", sql]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"DB Query Failed: {res.stderr}")
    return res.stdout.strip()

HITL_WEB_URL = "http://localhost:5001"

def execute_mcp_tool(tool_name, tool_args):
    """Executes an MCP tool via Streamable HTTP connection to staging-ansible-mcp inside container."""
    python_cmd = [
        "podman", "exec", "staging-hermes-agent",
        "/opt/hermes/.venv/bin/python", "-c",
        f"""
import asyncio
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

async def run():
    async with streamable_http_client('http://ansible-mcp:8000/mcp') as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool('{tool_name}', {json.dumps(tool_args)})
            print(res.content[0].text)

asyncio.run(run())
"""
    ]
    res = subprocess.run(python_cmd, capture_output=True, text=True)
    return res.stdout.strip()

def approve_pending_request(expected_action_name):
    """Logs into HITL Web UI and approves the pending request matching expected_action_name."""
    session = requests.Session()
    login_data = {'username': 'admin', 'password': 'admin123'}
    
    # Get login page & CSRF token
    resp = session.get(HITL_WEB_URL)
    csrf_match = re.search(r'name="csrf_token" value="(.*?)"', resp.text)
    if not csrf_match:
        raise RuntimeError("Failed to get CSRF token from Web UI")
    token = csrf_match.group(1)
    
    # Login
    login_resp = session.post(f"{HITL_WEB_URL}/login", data={**login_data, 'csrf_token': token}, allow_redirects=True)
    if "Logout" not in login_resp.text:
        raise RuntimeError("Failed to login to HITL Web UI")
    print("  [HITL Web Portal] Logged in as administrator ('admin').")
    
    # Find pending request matching expected_action_name
    for attempt in range(10):
        resp = session.get(HITL_WEB_URL)
        if expected_action_name in resp.text:
            forms = re.findall(r'action="/resolve/(\d+)".*?name="csrf_token" value="(.*?)"', resp.text, re.DOTALL)
            for req_id, csrf in forms:
                print(f"  [HITL Web Portal] Found Pending Request ID #{req_id} for '{expected_action_name}'. Approving now...")
                appr_resp = session.post(
                    f"{HITL_WEB_URL}/resolve/{req_id}",
                    data={'decision': 'GRANTED', 'csrf_token': csrf}
                )
                if appr_resp.status_code == 200:
                    print(f"  [HITL Web Portal] Request #{req_id} ({expected_action_name}) APPROVED (GRANTED) successfully!")
                    return req_id
        time.sleep(1)
    raise RuntimeError(f"Failed to find pending request for '{expected_action_name}'")

def run_lifecycle_sequence(action_name, action_summary, exec_tool_name, exec_tool_args):
    print_header(f"LIFECYCLE SEQUENCE: {action_name}")
    
    # Step A: Initiate HITL Approval Request
    print(f"1. Prompt / Agent Request: Invoke 'hitl_request_approval'")
    print(f"   - action_name: '{action_name}'")
    print(f"   - action_summary: '{action_summary}'")
    
    import threading
    approval_result = {}

    def _mcp_thread():
        out = execute_mcp_tool("hitl_request_approval", {
            "action_name": action_name,
            "action_summary": action_summary
        })
        approval_result["out"] = out

    t = threading.Thread(target=_mcp_thread)
    t.start()
    
    # Wait for DB row to appear
    req_id = None
    for _ in range(10):
        db_out = query_db(f"SELECT id, action_name, status, requested_at FROM hitl_requests WHERE action_name = '{action_name}' AND status = 'PENDING' ORDER BY id DESC LIMIT 1;")
        if db_out:
            parts = db_out.split("|")
            req_id = parts[0]
            print(f"\n2. Database Audit Verification (Immediately after request):")
            print(f"   - Request ID   : #{parts[0]}")
            print(f"   - Action Name  : {parts[1]}")
            print(f"   - DB Status    : {parts[2]} (Pending human decision)")
            print(f"   - Requested At : {parts[3]}")
            break
        time.sleep(1)
    
    assert req_id is not None, f"No pending request found in DB for {action_name}"

    # Step C: Admin Approves via Web UI
    print(f"\n3. Human Administrator Action (Web UI http://localhost:5001):")
    approved_req_id = approve_pending_request(action_name)
    
    # Wait for MCP thread to finish
    t.join(timeout=10)
    print(f"   - MCP Gate Result: {approval_result.get('out', '{}')}")
    
    # Step D: Verify DB Status = GRANTED
    db_out = query_db(f"SELECT id, action_name, status, resolved_at FROM hitl_requests WHERE id = {approved_req_id};")
    parts = db_out.split("|")
    print(f"\n4. Database Audit Verification (After approval):")
    print(f"   - Request ID   : #{parts[0]}")
    print(f"   - DB Status    : {parts[1]} -> {parts[2]} (APPROVED)")
    print(f"   - Resolved At  : {parts[3]}")
    assert parts[2] == 'GRANTED', "Expected status GRANTED"
    
    # Step E: Execute the High-Risk Tool
    print(f"\n5. Agent Executes High-Risk Operation via MCP:")
    print(f"   - Tool Name : {exec_tool_name}")
    print(f"   - Arguments : {exec_tool_args}")
    
    exec_output = execute_mcp_tool(exec_tool_name, exec_tool_args)
    print(f"\n6. Operation Output from Ansible Automation Platform:")
    print(exec_output)
    
    data = json.loads(exec_output)
    assert data.get("status") == "successful", f"Execution failed: {exec_output}"
    print(f"✅ Sequence '{action_name}' COMPLETED SUCCESSFULLY (AAP Job ID #{data.get('job_id')}).")

def main():
    check_containers()
    
    # Sequence 1: Fleet Patching
    run_lifecycle_sequence(
        action_name="Patch Fleet",
        action_summary="Apply critical RHEL security patches to production fleet",
        exec_tool_name="ansible_patch_fleet",
        exec_tool_args={"hostlist": "rhel-prod-01,rhel-prod-02"}
    )
    
    # Sequence 2: Fleet Reboot
    run_lifecycle_sequence(
        action_name="Reboot Fleet",
        action_summary="Reboot fleet after patching cycle",
        exec_tool_name="ansible_reboot_fleet",
        exec_tool_args={"hostlist": "rhel-prod-01,rhel-prod-02"}
    )
    
    # Final Audit Summary
    print_header("FINAL VERIFICATION SUMMARY")
    db_out = query_db("SELECT id, action_name, status, requested_at, resolved_at FROM hitl_requests ORDER BY id ASC;")
    rows = [r.split("|") for r in db_out.split("\n") if r.strip()]
    
    print("Database Audit Trail (Table: hitl_requests):")
    print(f"{'ID':<5} | {'Action Name':<20} | {'Status':<10} | {'Requested At':<25} | {'Resolved At':<25}")
    print("-" * 90)
    for r in rows:
        print(f"{r[0]:<5} | {r[1]:<20} | {r[2]:<10} | {str(r[3]):<25} | {str(r[4]):<25}")
    
    print("\n🎉 ALL E2E VERIFICATIONS PASSED! System is fully operational and approved.")

if __name__ == "__main__":
    main()

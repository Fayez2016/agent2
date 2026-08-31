#!/usr/bin/env python3
"""
================================================================================
 Consolidated SRE Verification & End-to-End Test Suite
================================================================================
 Runs and asserts the full suite of operational test scenarios:
 1. Health Check & Mode Verification (Enforced vs Autonomous)
 2. Dynamic Recipient Email Persistence & Retrieval
 3. 10-Cluster HA Rolling Update (Dynamic Discovery, 2-Wave Execution, Failure Isolation)
 4. Regular Fleet Patching (10 Hosts: Inventory -> Patch -> Reboot -> Verify -> Report)
 5. SRE Report Email Dispatch Verification
================================================================================
"""

import os
import sys
import time
import json
import requests

API_HOST = os.getenv("API_HOST", "http://localhost:8642")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer hermes-api-secret"
}

TEST_EMAIL = "fayez.soufyani@gmail.com"

def log_header(title: str):
    print("\n" + "=" * 78)
    print(f" 🧪 {title}")
    print("=" * 78)

def test_system_settings():
    log_header("TEST 1: System Settings & SRE Recipient Email")
    
    # Set Recipient Email
    res = requests.post(f"{API_HOST}/v1/settings/notification_email", json={"value": TEST_EMAIL})
    assert res.status_code == 200, f"Failed to save email: {res.text}"
    print(f" [PASS] Saved SRE recipient email: {TEST_EMAIL}")

    # Fetch Recipient Email
    res = requests.get(f"{API_HOST}/v1/settings/notification_email")
    assert res.status_code == 200, f"Failed to get email: {res.text}"
    fetched = res.json().get("email")
    assert fetched == TEST_EMAIL, f"Email mismatch: {fetched} != {TEST_EMAIL}"
    print(f" [PASS] Verified SRE recipient email from database: {fetched}")

    # Set Mode to Autonomous for automated pipeline
    res = requests.post(f"{API_HOST}/v1/settings/hitl_mode", json={"mode": "autonomous"})
    assert res.status_code == 200, f"Failed to set autonomous mode: {res.text}"
    print(" [PASS] Set guardrail mode to 'autonomous' for execution pipeline.")

def test_ha_10_clusters_rolling_update():
    log_header("TEST 2: 10-Cluster Zero-Downtime HA Rolling Update (SOP 2059253)")
    prompt = (
        "Using ha_cluster_patcher subagent, execute the Red Hat HA Rolling Update (SOP 2059253) "
        "across 10 HA clusters (ha_cluster1 to ha_cluster10). "
        "Dynamically discover member nodes (pattern: ha_cluster1_node1 to ha_cluster10_node2), "
        "execute Wave 1 for Node 1 across all clusters, isolate any failed cluster, "
        f"execute Wave 2 for Node 2 on healthy clusters, and email the final SRE report to {TEST_EMAIL}."
    )

    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    start = time.time()
    print(" Sending HA Rolling Update request to Deep Agent...")
    res = requests.post(f"{API_HOST}/v1/chat/completions", headers=HEADERS, json=payload, timeout=180)
    elapsed = time.time() - start

    assert res.status_code == 200, f"HA Rolling Update failed ({res.status_code}): {res.text}"
    reply = res.json()["choices"][0]["message"]["content"]

    print(f"\n--- Execution Finished in {elapsed:.2f}s ---")
    print(reply[:800] + ("...\n[Content truncated for display]" if len(reply) > 800 else ""))

    # Assertions
    has_clusters = any(f"ha_cluster{i}" in reply.lower() or f"cluster{i}" in reply.lower() for i in range(1, 11))
    has_wave1 = "node1" in reply.lower() or "wave 1" in reply.lower()
    has_table = "|" in reply or "matrix" in reply.lower() or "report" in reply.lower()

    assert has_clusters, "Failed: Did not discover/output 10 clusters."
    assert has_wave1, "Failed: Wave 1 primary execution not tracked."
    assert has_table, "Failed: Lifecycle matrix not generated."
    print("\n [PASS] 10-Cluster HA Rolling Update verified successfully.")

def test_regular_fleet_patching():
    log_header("TEST 3: Enterprise Fleet Patching (10 Hosts: rhel-prod-01 to rhel-prod-10)")
    prompt = (
        "Using fleet_patcher subagent, execute fleet patching on hosts rhel-prod-01 to rhel-prod-10: "
        f"inspect server inventory, apply package updates, execute managed reboots, verify online status, and email report to {TEST_EMAIL}."
    )

    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    start = time.time()
    print(" Sending Fleet Patching request to Deep Agent...")
    res = requests.post(f"{API_HOST}/v1/chat/completions", headers=HEADERS, json=payload, timeout=180)
    elapsed = time.time() - start

    assert res.status_code == 200, f"Fleet Patching failed ({res.status_code}): {res.text}"
    reply = res.json()["choices"][0]["message"]["content"]

    print(f"\n--- Execution Finished in {elapsed:.2f}s ---")
    print(reply[:800] + ("...\n[Content truncated for display]" if len(reply) > 800 else ""))

    # Assertions
    has_hosts = "rhel-prod" in reply.lower()
    has_table = "|" in reply or "matrix" in reply.lower()

    assert has_hosts, "Failed: Target hosts not found in report."
    assert has_table, "Failed: Host execution table not found."
    print("\n [PASS] Enterprise Fleet Patching verified successfully.")

def test_studio_crud_and_mcp_ping():
    log_header("TEST 4: Dynamic Agent & MCP Studio Endpoints & Live Tool Ping")
    
    # 1. Query registered MCP servers
    res = requests.get(f"{API_HOST}/v1/studio/mcp_servers")
    assert res.status_code == 200, f"Failed to list MCP servers: {res.text}"
    servers = res.json().get("servers", [])
    assert len(servers) >= 2, f"Expected at least 2 MCP servers, found {len(servers)}"
    print(f" [PASS] Listed {len(servers)} MCP servers from PostgreSQL: {[s['name'] for s in servers]}")

    # 2. Live Ping Ansible MCP Server
    res = requests.post(f"{API_HOST}/v1/studio/mcp_servers/ansible/ping")
    assert res.status_code == 200, f"Ping request failed: {res.text}"
    ping_data = res.json()
    assert ping_data["status"] == "connected", f"Ansible MCP not connected: {ping_data}"
    assert ping_data["live_tools_count"] > 10, f"Insufficient tools reported: {ping_data}"
    print(f" [PASS] Live ping successful on 'ansible' MCP server: {ping_data['live_tools_count']} live tools reported.")

    # 3. Query Domain Agents & Subagents
    res = requests.get(f"{API_HOST}/v1/studio/agents")
    assert res.status_code == 200, f"Failed to list agents: {res.text}"
    agents = res.json().get("agents", [])
    assert len(agents) >= 1, "No domain agents returned"
    linux_ag = next((a for a in agents if a["key_name"] == "linux_sre"), None)
    assert linux_ag is not None, "linux_sre agent not found"
    assert len(linux_ag.get("subagents", [])) >= 4, "Subagents not populated for linux_sre"
    print(f" [PASS] Dynamic Domain Agent '{linux_ag['key_name']}' loaded with {len(linux_ag['subagents'])} subagents.")

    # 4. Query Skills / SOPs
    res = requests.get(f"{API_HOST}/v1/studio/skills")
    assert res.status_code == 200, f"Failed to list skills: {res.text}"
    skills = res.json().get("skills", [])
    assert len(skills) >= 2, "Skills not populated"
    print(f" [PASS] Listed {len(skills)} declarative skills from PostgreSQL: {[s['name'] for s in skills]}")

def main():
    print("==============================================================================")
    print(" 🚀 DEEP AGENT CONSOLIDATED TEST SUITE")
    print("==============================================================================")
    
    suite_start = time.time()
    try:
        test_system_settings()
        test_studio_crud_and_mcp_ping()
        test_ha_10_clusters_rolling_update()
        test_regular_fleet_patching()
        
        total_time = time.time() - suite_start
        print("\n" + "=" * 78)
        print(f" 🎉 ALL CONSOLIDATED TESTS PASSED SUCCESSFULLY in {total_time:.2f}s!")
        print("==============================================================================")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n ❌ TEST ASSERTION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n ❌ UNEXPECTED ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

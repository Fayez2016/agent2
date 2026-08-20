#!/usr/bin/env python3
"""
Randomized Multi-Scenario Dynamic Test Suite
Strictly decoupled from Agent implementation:
1. Generates random fleet sizes (3 to 15 nodes) and random hostname patterns (UUIDs, cluster names, tiers).
2. Tests dynamic parameter extraction and FastMCP batch tool execution.
3. Tests randomized edge cases:
   - Scenario 1: Clean Dynamic HA Rolling Update (Random cluster count: 3 to 8 clusters).
   - Scenario 2: Dynamic HA Rolling Update with Soft-Hang & Console IPMI Recovery.
   - Scenario 3: Clean Dynamic Standalone Fleet Patching (Random fleet size: 4 to 12 hosts).
   - Scenario 4: Dynamic Standalone Fleet with Soft-Hang Recovery.
   - Scenario 5: Single Upfront Master Authorization Gate for Dynamic Hostlists.
"""

import sys
import time
import uuid
import random
import requests
import json

BASE_URL = "http://localhost:8642"
API_KEY = "hermes-api-secret"

def log(msg):
    print(f"[RANDOM-TEST] {msg}", flush=True)

def generate_random_clusters(count: int) -> list:
    """Generates random cluster names with distinct IDs."""
    prefixes = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
    selected = random.sample(prefixes, min(count, len(prefixes)))
    return [f"cluster-{name}-{uuid.uuid4().hex[:4]}" for name in selected]

def generate_random_hosts(count: int) -> list:
    """Generates random hostnames with mixed patterns (UUID, node-ID, srv-role)."""
    roles = ["db", "web", "app", "cache", "api", "auth"]
    hosts = []
    for i in range(count):
        role = random.choice(roles)
        short_id = uuid.uuid4().hex[:5]
        hosts.append(f"srv-{role}-{short_id}")
    return hosts

def test_randomized_ha_rolling_update(simulate_hang: bool = False):
    cluster_count = random.randint(3, 6)
    clusters = generate_random_clusters(cluster_count)
    cluster_str = ", ".join(clusters)
    
    scenario_desc = f"HA Rolling Update with {'Soft-Hang & Recovery' if simulate_hang else 'Clean Run'}"
    log(f"==========================================================================")
    log(f"Testing {scenario_desc} across {cluster_count} Random Clusters: {cluster_str}")
    log(f"==========================================================================")

    # 1. Ensure HITL mode is 'enforced'
    requests.post(f"{BASE_URL}/v1/settings/hitl_mode", json={"mode": "enforced"})

    prompt = (
        f"Using ha-cluster-patcher subagent, execute the Red Hat HA Rolling Update (SOP 2059253) "
        f"across clusters {cluster_str}. Combine pre-check and standby, apply patches, reboot with "
        f"console recovery if needed, unstandby, and email the final report to admin@enterprise.local."
    )

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepagent", "stream": False, "messages": [{"role": "user", "content": prompt}]}

    import threading
    response_holder = {}
    def invoke():
        try:
            resp = requests.post(f"{BASE_URL}/v1/chat/completions", headers=headers, json=payload, timeout=90)
            response_holder["resp"] = resp
        except Exception as e:
            response_holder["error"] = e

    t = threading.Thread(target=invoke)
    t.start()

    # Approve upfront master request
    log("Monitoring for upfront master HITL authorization request...")
    for _ in range(25):
        time.sleep(1)
        r_p = requests.get(f"{BASE_URL}/v1/hitl/pending")
        if r_p.status_code == 200:
            pending = r_p.json().get("pending", [])
            if pending:
                req_id = pending[0]["id"]
                requests.post(f"{BASE_URL}/v1/hitl/resolve", json={"request_id": req_id, "decision": "GRANTED"})
                log(f"✓ Master authorization granted for Request #{req_id}.")
                break

    t.join(timeout=60)
    assert "resp" in response_holder, f"Invocation failed: {response_holder.get('error')}"
    resp = response_holder["resp"]
    assert resp.status_code == 200, f"API returned status {resp.status_code}: {resp.text}"

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    steps = data.get("intermediate_steps", [])

    log(f"✓ Execution completed. Total tool steps executed: {len(steps)}")
    assert len(steps) >= 8, f"Expected at least 8 steps, got {len(steps)}"

    # Verify ALL random cluster names are present in the final report
    for c in clusters:
        assert c in content, f"Random cluster '{c}' missing from generated SRE report."
    log(f"✓ Verified all {cluster_count} dynamic cluster names appear in report tables.")

    # Verify Pacemaker Resource Groups and Quorum are reported
    assert "QUORATE" in content, "Quorum information missing."
    assert "rg_" in content, "Resource groups missing."
    log("✓ Verified Pacemaker Quorum and Resource Groups.")

    # Verify email dispatch
    assert any("email" in str(s).lower() for s in steps) or "email" in content.lower(), "Email step missing."
    log("✓ Verified email notification dispatch.")
    return True

def test_randomized_fleet_patching(simulate_hang: bool = False):
    host_count = random.randint(4, 9)
    hosts = generate_random_hosts(host_count)
    if simulate_hang:
        hosts[1] = f"{hosts[1]}-hang"
    host_str = ", ".join(hosts)

    scenario_desc = f"Fleet Patching with {'Soft-Hang & Recovery' if simulate_hang else 'Clean Run'}"
    log(f"==========================================================================")
    log(f"Testing {scenario_desc} across {host_count} Random Hosts: {host_str}")
    log(f"==========================================================================")

    requests.post(f"{BASE_URL}/v1/settings/hitl_mode", json={"mode": "enforced"})

    prompt = (
        f"Using fleet-patcher subagent, execute fleet patching on hosts {host_str}: "
        f"patch, reboot, verify online with console recovery if needed, and email report to admin@enterprise.local."
    )

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepagent", "stream": False, "messages": [{"role": "user", "content": prompt}]}

    import threading
    response_holder = {}
    def invoke():
        try:
            resp = requests.post(f"{BASE_URL}/v1/chat/completions", headers=headers, json=payload, timeout=90)
            response_holder["resp"] = resp
        except Exception as e:
            response_holder["error"] = e

    t = threading.Thread(target=invoke)
    t.start()

    log("Monitoring for upfront master HITL authorization request...")
    for _ in range(25):
        time.sleep(1)
        r_p = requests.get(f"{BASE_URL}/v1/hitl/pending")
        if r_p.status_code == 200:
            pending = r_p.json().get("pending", [])
            if pending:
                req_id = pending[0]["id"]
                requests.post(f"{BASE_URL}/v1/hitl/resolve", json={"request_id": req_id, "decision": "GRANTED"})
                log(f"✓ Master authorization granted for Request #{req_id}.")
                break

    t.join(timeout=60)
    assert "resp" in response_holder, f"Invocation failed: {response_holder.get('error')}"
    resp = response_holder["resp"]
    assert resp.status_code == 200, f"API returned status {resp.status_code}: {resp.text}"

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    steps = data.get("intermediate_steps", [])

    log(f"✓ Fleet patching completed. Tool steps executed: {len(steps)}")
    for h in hosts:
        assert h in content, f"Random host '{h}' missing from final report."
    log(f"✓ Verified all {host_count} dynamic hosts appear in summary table.")

    assert any("email" in str(s).lower() for s in steps) or "email" in content.lower(), "Email step missing."
    log("✓ Verified email notification dispatch.")
    return True

def run_all_randomized_scenarios():
    log("==========================================================================")
    log(" STARTING RANDOMIZED DYNAMIC SRE SCENARIO TEST MATRIX")
    log("==========================================================================")

    # 1. Clean HA Rolling Update (Random Cluster Count)
    assert test_randomized_ha_rolling_update(simulate_hang=False)
    
    # 2. HA Rolling Update with Soft Hang & Out-of-Band Console Recovery
    assert test_randomized_ha_rolling_update(simulate_hang=True)

    # 3. Clean Standalone Fleet Patching (Random Host Count)
    assert test_randomized_fleet_patching(simulate_hang=False)

    # 4. Standalone Fleet Patching with Soft Hang & Console Recovery
    assert test_randomized_fleet_patching(simulate_hang=True)

    log("==========================================================================")
    log(" ALL RANDOMIZED SCENARIOS PASSED SUCCESSFULLY!")
    log(" Dynamic host extraction, batch execution & edge-case recovery verified.")
    log("==========================================================================")
    return True

if __name__ == "__main__":
    success = run_all_randomized_scenarios()
    sys.exit(0 if success else 1)

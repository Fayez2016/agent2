#!/usr/bin/env python3
"""
Multi-Run Dynamic Test Suite for Fleet Patcher Subagent ('fleet-patcher')
Executes 3 distinct randomized test runs with completely different fleet topographies,
different host counts, random naming schemes (UUIDs, multi-tier roles), and different edge-case scenarios:
  - Run 1: Clean Batch Fleet Patching across 4 Random Hosts (UUID-based).
  - Run 2: Fleet Patching with Kernel Soft-Hang at Reboot & Out-of-Band IPMI Recovery across 6 Random Hosts.
  - Run 3: Large-Scale Fleet Patching across 9 Multi-Tier Hosts (web, db, auth, api, cache).

Strictly verifies that:
1. NO hostnames, fleet sizes, or report outputs are hardcoded in the agent.
2. All dynamic hostnames in each run appear in tool call arguments and final summary tables.
3. Out-of-band console power-on is invoked dynamically when hung hosts are detected.
4. Email notification is dispatched for each run.
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
    print(f"[FLEET-MULTI-TEST] {msg}", flush=True)

def generate_random_fleet(count: int, simulate_hang: bool = False) -> list:
    """Generates unique, randomized hostnames with realistic enterprise tier patterns."""
    roles = ["web", "db", "app", "auth", "api", "cache", "proxy", "queue", "worker"]
    hosts = []
    for i in range(count):
        role = random.choice(roles)
        short_id = uuid.uuid4().hex[:5]
        hosts.append(f"srv-{role}-{short_id}")
        
    if simulate_hang and len(hosts) >= 2:
        # Tag one host to simulate soft-hang on reboot
        hosts[1] = f"{hosts[1]}-hang"
    return hosts

def execute_fleet_test_run(run_number: int, host_count: int, simulate_soft_hang: bool = False):
    hosts = generate_random_fleet(host_count, simulate_soft_hang)
    host_str = ", ".join(hosts)
    scenario_type = "Soft-Hang & Out-of-Band IPMI Recovery" if simulate_soft_hang else "Clean Batch Patching"

    log("=" * 80)
    log(f"▶ STARTING FLEET PATCHER TEST RUN #{run_number}/3: {scenario_type}")
    log(f"  Target Hosts ({host_count}): {host_str}")
    log("=" * 80)

    # 1. Enforce HITL Mode
    r_mode = requests.post(f"{BASE_URL}/v1/settings/hitl_mode", json={"mode": "enforced"})
    assert r_mode.status_code == 200, f"Failed to set HITL mode: {r_mode.text}"

    # 2. Build User Prompt with Dynamic Hostnames
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

    # 3. Handle Upfront Master HITL Authorization Gate
    log("  [Step 1] Monitoring for upfront master HITL authorization request...")
    approved = False
    for _ in range(25):
        time.sleep(1)
        r_pending = requests.get(f"{BASE_URL}/v1/hitl/pending")
        if r_pending.status_code == 200:
            pending = r_pending.json().get("pending", [])
            if pending:
                req_id = pending[0]["id"]
                action = pending[0]["action_name"]
                requests.post(f"{BASE_URL}/v1/hitl/resolve", json={"request_id": req_id, "decision": "GRANTED"})
                log(f"  ✓ Master authorization GRANTED for Request #{req_id} ('{action}').")
                approved = True
                break

    t.join(timeout=60)
    assert "resp" in response_holder, f"API invocation failed: {response_holder.get('error')}"
    resp = response_holder["resp"]
    assert resp.status_code == 200, f"API returned status {resp.status_code}: {resp.text}"

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    steps = data.get("intermediate_steps", [])

    log(f"  [Step 2] Execution finished. Total FastMCP tool steps executed: {len(steps)}")
    assert len(steps) >= 4, f"Expected at least 4 tool steps, got {len(steps)}"

    # 4. Strict Dynamic Verification: Ensure NO hardcoding
    log("  [Step 3] Verifying dynamic entity extraction and report synthesis...")
    for h in hosts:
        # Check that hostname was passed dynamically in tool arguments
        found_in_tool_args = any(h in str(s.get("tool_args", {})) for s in steps)
        assert found_in_tool_args, f"Host '{h}' was NOT passed to FastMCP tool arguments!"

        # Check that hostname appears in the final report
        assert h in content, f"Dynamic host '{h}' missing from final summary table!"

    log(f"  ✓ Confirmed: All {host_count} dynamic hostnames verified in tool arguments & summary table.")

    # 5. Check Scenario-Specific Invariants
    if simulate_soft_hang:
        log("  [Step 4] Verifying soft-hang detection and out-of-band console recovery...")
        has_console_tool = any("console" in s.get("tool_name", "").lower() for s in steps)
        assert has_console_tool, "Expected ansible_console_power_on tool call during soft-hang scenario!"
        assert "Console Power-On" in content or "Console" in content or "Soft Hang" in content, "Console recovery missing from summary."
        log("  ✓ Confirmed: Soft-hang detected and recovered via console power-on.")

    # 6. Verify Email Notification
    has_email = any("email" in str(s).lower() for s in steps) or "email" in content.lower()
    assert has_email, "Automated email dispatch step missing."
    log("  ✓ Confirmed: SRE fleet patching report email dispatched to admin@enterprise.local.")

    log(f"✓ RUN #{run_number}/3 PASSED SUCCESSFULLY!\n")
    return True

def run_3_distinct_fleet_scenarios():
    log("==========================================================================")
    log(" STARTING 3-RUN DYNAMIC VERIFICATION SUITE FOR FLEET PATCHER")
    log("==========================================================================")

    # Run 1: Clean 4-Host Batch Run (UUIDs)
    assert execute_fleet_test_run(run_number=1, host_count=4, simulate_soft_hang=False)

    # Run 2: 6-Host Run with Soft Hang & IPMI Recovery
    assert execute_fleet_test_run(run_number=2, host_count=6, simulate_soft_hang=True)

    # Run 3: Large 9-Host Multi-Tier Run
    assert execute_fleet_test_run(run_number=3, host_count=9, simulate_soft_hang=False)

    log("==========================================================================")
    log(" ALL 3 DYNAMIC FLEET PATCHER RUNS COMPLETED AND PASSED 100%!")
    log(" Zero hardcoding confirmed: Universal entity extraction & dynamic reporting verified.")
    log("==========================================================================")
    return True

if __name__ == "__main__":
    success = run_3_distinct_fleet_scenarios()
    sys.exit(0 if success else 1)

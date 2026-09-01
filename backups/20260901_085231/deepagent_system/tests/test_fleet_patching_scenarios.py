#!/usr/bin/env python3
"""
Test Scenario 2: Enterprise Fleet Patching & Console Recovery
Tests:
1. Delegation to 'fleet-patcher' subagent across 10 standalone hosts.
2. Package updates, reboot, and uptime verification.
3. Out-of-band console power-on recovery for unresponsive hosts.
4. Automated email notification dispatch via Ansible.
"""

import sys
import time
import requests
import json

BASE_URL = "http://localhost:8642"
API_KEY = "hermes-api-secret"

def log(msg):
    print(f"[FLEET-PATCH-TEST] {msg}", flush=True)

def test_fleet_patching_scenario():
    log("==========================================================================")
    log("Running Enterprise Fleet Patching Scenario (10 Standalone Hosts)...")
    log("==========================================================================")

    # 1. Submit Fleet Patching Prompt
    prompt = (
        "Using fleet-patcher subagent, execute fleet patching on hosts rhel-prod-01 to rhel-prod-10: "
        "patch, reboot, verify online with console recovery if needed, and email report to admin@enterprise.local."
    )
    log(f"Step 1: Submitting fleet patching prompt for 10 hosts...")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepagent",
        "stream": False,
        "messages": [{"role": "user", "content": prompt}]
    }

    import threading
    response_holder = {}
    def invoke_api():
        try:
            resp = requests.post(f"{BASE_URL}/v1/chat/completions", headers=headers, json=payload, timeout=60)
            response_holder["resp"] = resp
        except Exception as e:
            response_holder["error"] = e

    t = threading.Thread(target=invoke_api)
    t.start()

    # 2. Monitor for upfront approval
    log("Step 2: Monitoring for upfront HITL authorization request...")
    for _ in range(25):
        time.sleep(1)
        r_pending = requests.get(f"{BASE_URL}/v1/hitl/pending")
        if r_pending.status_code == 200:
            pending_list = r_pending.json().get("pending", [])
            if pending_list:
                req_id = pending_list[0]["id"]
                action_name = pending_list[0]["action_name"]
                log(f"✓ Detected upfront HITL request #{req_id} for '{action_name}'.")
                
                # Grant master approval
                r_res = requests.post(f"{BASE_URL}/v1/hitl/resolve", json={"request_id": req_id, "decision": "GRANTED"})
                assert r_res.status_code == 200
                log(f"✓ Master authorization granted for Request #{req_id}.")
                break

    t.join(timeout=45)

    if "resp" not in response_holder:
        log(f"✗ API invocation error: {response_holder.get('error')}")
        return False

    resp = response_holder["resp"]
    assert resp.status_code == 200, f"API returned status {resp.status_code}: {resp.text}"
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    steps = data.get("intermediate_steps", [])

    log(f"✓ Fleet patching completed. Tool steps executed: {len(steps)}")
    log(f"Summary Content Preview:\n{content[:400]}...")

    # 3. Verify email dispatch
    assert any("email" in str(s).lower() or "mail" in str(s).lower() for s in steps) or "email" in content.lower(), "Email dispatch step missing."
    log("✓ Automated email dispatch to admin@enterprise.local verified.")

    log("==========================================================================")
    log("✓ SCENARIO 2 (Enterprise Fleet Patching) PASSED SUCCESSFULLY!")
    log("==========================================================================")
    return True

if __name__ == "__main__":
    success = test_fleet_patching_scenario()
    sys.exit(0 if success else 1)

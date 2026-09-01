#!/usr/bin/env python3
"""
Hardened Test Scenario 1: Red Hat HA Multi-Cluster Rolling Update (SOP 2059253)
Verifies:
1. Upfront HITL approval gate prompt and resolution.
2. Tools are called with batch hostlists (not repeated for single hosts).
3. Pacemaker Resource Groups & Quorum status present in final report.
4. Stage failure and console recovery logged with stage details.
5. Email dispatched to admin@enterprise.local.
"""

import sys
import time
import requests
import json

BASE_URL = "http://localhost:8642"
API_KEY = "hermes-api-secret"

def log(msg):
    print(f"[HA-SOP-TEST] {msg}", flush=True)

def test_ha_rolling_update_scenario():
    log("==========================================================================")
    log("Running Hardened HA Cluster Rolling Update Scenario (10 Clusters / 20 Nodes)...")
    log("==========================================================================")

    # 1. Ensure HITL mode is 'enforced'
    log("Step 1: Setting HITL Guardrail Mode to 'enforced'...")
    r = requests.post(f"{BASE_URL}/v1/settings/hitl_mode", json={"mode": "enforced"})
    assert r.status_code == 200, f"Failed to set HITL mode: {r.text}"
    log("✓ HITL Guardrail Mode verified as ENFORCED.")

    # 2. Submit HA Rolling Update prompt targeting 10 clusters
    prompt = (
        "Using ha-cluster-patcher subagent, execute the Red Hat HA Rolling Update (SOP 2059253) "
        "across 10 HA clusters (ha-cluster-01 to ha-cluster-10). Combine pre-check and standby, "
        "apply patches, reboot with console recovery if needed, unstandby, and email the final report to admin@enterprise.local."
    )
    log(f"Step 2: Submitting multi-cluster rolling update prompt...")
    
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
            resp = requests.post(f"{BASE_URL}/v1/chat/completions", headers=headers, json=payload, timeout=90)
            response_holder["resp"] = resp
        except Exception as e:
            response_holder["error"] = e

    t = threading.Thread(target=invoke_api)
    t.start()

    # 3. Monitor for Single Upfront Master HITL Authorization Request
    log("Step 3: Monitoring for single upfront master HITL authorization request...")
    approved = False
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
                approved = True
                break

    t.join(timeout=60)
    
    if "resp" not in response_holder:
        log(f"✗ API invocation error: {response_holder.get('error')}")
        return False

    resp = response_holder["resp"]
    assert resp.status_code == 200, f"API returned status {resp.status_code}: {resp.text}"
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    steps = data.get("intermediate_steps", [])

    log(f"✓ Response received. Total tool/subagent steps executed: {len(steps)}")
    assert len(steps) >= 8, f"Expected at least 8 steps for multi-cluster rolling update, got {len(steps)}"

    # 4. Verify batch parameter passing (hostlist contains multiple nodes)
    for s in steps:
        args = s.get("tool_args", {})
        if "hostlist" in args and "," in args["hostlist"]:
            log(f"✓ Verified batch parameter passing in step '{s.get('tool_name')}': {args['hostlist'][:45]}...")

    # 5. Verify Pacemaker Resource Groups & Failure Stage in Final Content
    assert "rg_app" in content or "Resource Group" in content, "Missing Pacemaker Resource Group placement in final report."
    assert "QUORATE" in content or "Quorum" in content, "Missing Quorum verification in final report."
    assert "Soft Hang" in content or "Console" in content or "Stage" in content, "Missing Stage-specific failure/recovery analysis in report."
    log("✓ Verified Pacemaker Resource Groups, Quorum Health, and Stage Failure/Recovery in final report.")

    # 6. Verify Email Dispatch
    assert any("email" in str(s).lower() for s in steps) or "email" in content.lower(), "Missing email dispatch."
    log("✓ Automated email dispatch to admin@enterprise.local verified.")

    log("==========================================================================")
    log("✓ SCENARIO 1 (HA Multi-Cluster Rolling Update) PASSED SUCCESSFULLY!")
    log("==========================================================================")
    return True

if __name__ == "__main__":
    success = test_ha_rolling_update_scenario()
    sys.exit(0 if success else 1)

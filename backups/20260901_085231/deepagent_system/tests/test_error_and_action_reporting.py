#!/usr/bin/env python3
"""
Comprehensive SRE Edge-Case & Error Reporting Test Suite
Validates that the final SRE report and email notification present:
1. Exact DNF Package Failure messages and stages for failed nodes.
2. Exact Pacemaker Resource Group degradation / failcount warnings.
3. Reboot soft-hang timeouts and out-of-band IPMI console recoveries.
4. Actionable Administrator Recommendations and Optimization steps.
"""

import sys
import time
import uuid
import requests
import json

BASE_URL = "http://localhost:8642"
API_KEY = "hermes-api-secret"

def log(msg):
    print(f"[ERROR-REPORT-TEST] {msg}", flush=True)

def test_fleet_patching_error_reporting():
    log("=" * 80)
    log("▶ TEST 1: Fleet Patching with DNF Failure & Soft-Hang Incidents")
    log("=" * 80)

    requests.post(f"{BASE_URL}/v1/settings/hitl_mode", json={"mode": "enforced"})

    hosts = ["srv-web-01", "srv-db-dnf-err", "srv-proxy-hang", "srv-auth-04"]
    host_str = ", ".join(hosts)
    prompt = f"Using fleet-patcher subagent, execute fleet patching on hosts {host_str}: patch, reboot, verify online with console recovery if needed, and email report to admin@enterprise.local."

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

    # Upfront master authorization
    for _ in range(25):
        time.sleep(1)
        r_p = requests.get(f"{BASE_URL}/v1/hitl/pending")
        if r_p.status_code == 200:
            pending = r_p.json().get("pending", [])
            if pending:
                req_id = pending[0]["id"]
                requests.post(f"{BASE_URL}/v1/hitl/resolve", json={"request_id": req_id, "decision": "GRANTED"})
                log(f"  ✓ Upfront authorization GRANTED for Request #{req_id}.")
                break

    t.join(timeout=60)
    assert "resp" in response_holder, f"Invocation failed: {response_holder.get('error')}"
    resp = response_holder["resp"]
    assert resp.status_code == 200, f"API returned {resp.status_code}: {resp.text}"

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    log("  [Verifying Report Content]")
    # 1. Verify DNF failure message is explicitly logged
    assert "srv-db-dnf-err" in content, "Failed host missing from report table."
    assert "FAILED (DNF Error)" in content or "DNF" in content, "DNF failure status missing from table."
    assert "Patching Failure on `srv-db-dnf-err`" in content, "Failure message missing from incident log."
    log("  ✓ Confirmed: Detailed DNF failure message rendered in Incident Log.")

    # 2. Verify Soft-Hang recovery is logged
    assert "srv-proxy-hang" in content, "Hung host missing from report table."
    assert "Console Power-On" in content or "Recovered" in content, "Console recovery missing."
    log("  ✓ Confirmed: Out-of-band console power-on recovery rendered.")

    # 3. Verify Administrator Action Items
    assert "Administrator Action Items" in content, "Action items section missing."
    assert "dnf clean all" in content or "Manual Action" in content, "Manual remediation instructions missing."
    log("  ✓ Confirmed: Actionable administrator remediation steps present in report.")

    log("✓ TEST 1 PASSED SUCCESSFULLY!\n")
    return True

def test_ha_rolling_update_error_reporting():
    log("=" * 80)
    log("▶ TEST 2: HA Rolling Update with Resource Group Warning & Node Recovery")
    log("=" * 80)

    requests.post(f"{BASE_URL}/v1/settings/hitl_mode", json={"mode": "enforced"})

    clusters = ["cluster-alpha-alert", "cluster-bravo-hang", "cluster-charlie"]
    cluster_str = ", ".join(clusters)
    prompt = f"Using ha-cluster-patcher subagent, execute Red Hat HA Rolling Update (SOP 2059253) across clusters {cluster_str}: pre-check and standby, patch, reboot, unstandby, and email report to admin@enterprise.local."

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

    for _ in range(25):
        time.sleep(1)
        r_p = requests.get(f"{BASE_URL}/v1/hitl/pending")
        if r_p.status_code == 200:
            pending = r_p.json().get("pending", [])
            if pending:
                req_id = pending[0]["id"]
                requests.post(f"{BASE_URL}/v1/hitl/resolve", json={"request_id": req_id, "decision": "GRANTED"})
                log(f"  ✓ Upfront authorization GRANTED for Request #{req_id}.")
                break

    t.join(timeout=60)
    assert "resp" in response_holder, f"Invocation failed: {response_holder.get('error')}"
    resp = response_holder["resp"]
    assert resp.status_code == 200, f"API returned {resp.status_code}: {resp.text}"

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    log("  [Verifying HA Report Content]")
    # 1. Verify Pacemaker Resource Group Degradation Warning
    assert "cluster-alpha-alert" in content, "Degraded cluster missing."
    assert "rg_cluster-alpha-alert" in content, "Resource group missing."
    assert "WARNING" in content or "Failcount" in content, "Resource warning missing from Quorum table."
    log("  ✓ Confirmed: Pacemaker resource group failcount warning rendered.")

    # 2. Verify Soft-Hang Recovery
    assert "cluster-bravo-hang" in content, "Hung node missing."
    assert "Console Power-On" in content or "Console" in content, "Console recovery missing."
    log("  ✓ Confirmed: Cluster node console recovery rendered.")

    # 3. Verify Administrator Action Items
    assert "Administrator Action Items" in content, "Action items section missing."
    assert "pcs resource cleanup" in content or "ansible_fix_pcs" in content or "Manual Action" in content, "Cleanup recommendations missing."
    log("  ✓ Confirmed: Cluster remediation & optimization recommendations present in report.")

    log("✓ TEST 2 PASSED SUCCESSFULLY!\n")
    return True

if __name__ == "__main__":
    assert test_fleet_patching_error_reporting()
    assert test_ha_rolling_update_error_reporting()
    log("==========================================================================")
    log(" ALL ERROR & ACTIONABLE REPORTING TESTS PASSED 100%!")
    log("==========================================================================")
    sys.exit(0)

#!/usr/bin/env python3
"""
================================================================================
 Automated Test Runner: Universal Subagent REST Invocation (UAT-EXT-13)
================================================================================
 Tests the complete end-to-end integration:
 1. Dedicated Scoped API Key generation (da_sec_*)
 2. Authentication and Authorization on /v1/chat/completions
 3. Invocation of all 4 subagents:
    - ha_cluster_patcher (SOP 2059253)
    - fleet_patcher (Batch fleet patching)
    - rhel_diagnostician (Cluster log diagnostics)
    - single_host_operator (Storage expansion / LVM)
 4. Thread auto-creation & PostgreSQL session persistence verification
 5. Instant Token Revocation (HTTP 401 verification)
================================================================================
"""

import sys
import time
import json
import requests

API_HOST = "http://localhost:8642"

def main():
    print("=" * 80)
    print(" 🚀 RUNNING UAT-EXT-13: UNIVERSAL SUBAGENT REST INTEGRATION BATTERY")
    print("=" * 80)

    # Step 1: Generate Dedicated Scoped API Token
    print("\n--- 1. Generating Dedicated Scoped API Token for ServiceNow Integration ---")
    tok_res = requests.post(f"{API_HOST}/v1/auth/tokens", json={
        "name": "ServiceNow Multi-Subagent Automation (Dedicated)",
        "scope": "read_write",
        "domain_category": "linux",
        "expiry_option": "30d"
    })
    assert tok_res.status_code == 200, f"Failed to generate token: {tok_res.text}"
    token_record = tok_res.json()["token_record"]
    raw_key = token_record["raw_token"]
    token_id = token_record["id"]
    print(f"✓ Dedicated Token Generated: ID={token_id}")
    print(f"✓ Bearer Key: {raw_key[:16]}...")
    print(f"✓ Domain Scope: {token_record['domain_category']}")

    headers = {"Authorization": f"Bearer {raw_key}", "Content-Type": "application/json"}

    # Subagent Test Battery
    tests = [
        {
            "subagent": "ha_cluster_patcher",
            "thread_id": "test_auto_ha_patch_01",
            "prompt": "Using ha_cluster_patcher subagent, execute the Red Hat HA Rolling Update (SOP 2059253) on cluster ha_cluster_01: discover nodes, apply wave 1 standby on node 1, patch, reboot, verify quorum, unstandby, and repeat wave 2 on node 2 with zero downtime."
        },
        {
            "subagent": "fleet_patcher",
            "thread_id": "test_auto_fleet_patch_02",
            "prompt": "Using fleet_patcher subagent, execute security patching and staged reboot across standalone nodes rhel-app-01 to rhel-app-04."
        },
        {
            "subagent": "rhel_diagnostician",
            "thread_id": "test_auto_diag_logs_03",
            "prompt": "Using rhel_diagnostician subagent, analyze /var/log/messages across cluster nodes for kernel panics and OOM events."
        },
        {
            "subagent": "single_host_operator",
            "thread_id": "test_auto_storage_expand_04",
            "prompt": "Using single_host_operator subagent, expand the /var/lib/pgsql filesystem by 15GB on rhel-db-01."
        }
    ]

    all_passed = True

    for idx, t in enumerate(tests, 1):
        print(f"\n--- 2.{idx}. Invoking Subagent: {t['subagent']} (Thread: {t['thread_id']}) ---")
        t0 = time.time()
        payload = {
            "model": "deepagent",
            "domain": "linux_sre",
            "thread_id": t["thread_id"],
            "messages": [{"role": "user", "content": t["prompt"]}],
            "stream": False
        }
        res = requests.post(f"{API_HOST}/v1/chat/completions", json=payload, headers=headers, timeout=90)
        dur = time.time() - t0
        
        if res.status_code == 200:
            data = res.json()
            steps = data.get("intermediate_steps", [])
            content = data["choices"][0]["message"]["content"]
            print(f"✓ Status: 200 OK ({dur:.2f}s) | Tool Steps Logged: {len(steps)}")
            print(f"✓ Response: {content[:180]}...")
            
            # Step 3: Verify PostgreSQL Thread Persistence
            th_res = requests.get(f"{API_HOST}/v1/threads/{t['thread_id']}/messages")
            th_msgs = th_res.json().get("messages", [])
            print(f"✓ PostgreSQL Thread Hydration Verified ({len(th_msgs)} messages saved)")
            assert len(th_msgs) >= 2, f"Expected at least 2 messages in thread {t['thread_id']}"
        else:
            print(f"✗ Failed: HTTP {res.status_code} - {res.text}")
            all_passed = False

    # Step 4: Test Instant Token Revocation
    print("\n--- 3. Testing Instant Token Revocation (Zero-Trust Security) ---")
    del_res = requests.delete(f"{API_HOST}/v1/auth/tokens/{token_id}")
    assert del_res.status_code == 200, "Failed to delete token"
    print(f"✓ Token ID {token_id} revoked from PostgreSQL")

    rev_res = requests.get(f"{API_HOST}/v1/auth/me", headers=headers)
    print(f"✓ Revoked Token Status: HTTP {rev_res.status_code} (Expected 401 Unauthorized)")
    assert rev_res.status_code == 401, f"Expected 401, got {rev_res.status_code}"

    print("\n" + "=" * 80)
    if all_passed:
        print(" 🎉 ALL UNIVERSAL SUBAGENT REST TESTS (UAT-EXT-13) PASSED (100% SUCCESS)")
    else:
        print(" ❌ SOME SUBAGENT TESTS FAILED")
    print("=" * 80)

if __name__ == "__main__":
    main()

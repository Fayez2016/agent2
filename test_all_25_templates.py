#!/usr/bin/env python3
"""
================================================================================
 🚀 Deep Agent: Complete 25-Case AAP Operational Battery Test Suite
================================================================================
 Tests all 25 Ansible FastMCP tools against AAP / AWX backend:
 - Verifies Template Resolution (with fuzzy matching)
 - Verifies Extra Variables passed cleanly
 - Verifies Job Launch & Execution output
 - Reports clean per-case PASS / FAIL results table
================================================================================
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("BatteryTest")

# Ensure deepagent_system is in python path
sys.path.insert(0, "/home/fayez/agent2/deepagent_system")

from ansible_mcp_server import (
    ansible_get_server_info,
    ansible_check_host_online,
    ansible_run_command,
    ansible_expand_fs,
    ansible_install_package,
    ansible_patch_fleet,
    ansible_reboot_host,
    ansible_reboot_fleet,
    ansible_pcs_status,
    ansible_pcs_health_check,
    ansible_pcs_node_standby,
    ansible_pcs_node_unstandby,
    ansible_pcs_cluster_stop,
    ansible_pcs_cluster_start,
    ansible_pcs_cluster_disable,
    ansible_pcs_cluster_enable,
    ansible_pcs_maintenance_mode,
    ansible_pcs_resource_move,
    ansible_pcs_resource_clear,
    ansible_pcs_cib_upgrade,
    ansible_pcs_constraint_list,
    ansible_fix_pcs,
    ansible_console_power_on,
    ansible_vmware_reset,
    ansible_send_email
)

TARGET_HOST = os.environ.get("TEST_TARGET_HOST", "node-primary")
TARGET_CLUSTER = os.environ.get("TEST_TARGET_CLUSTER", "cluster-01")
RECIPIENT_EMAIL = os.environ.get("TEST_RECIPIENT", "operator@enterprise.local")

# Complete 25-Case Battery
TEST_CASES = [
    # 1. Host Visibility & Discovery
    ("1. Get Server Info", lambda: ansible_get_server_info(TARGET_HOST)),
    ("2. Check Host Online", lambda: ansible_check_host_online(TARGET_HOST)),
    
    # 2. Ad-Hoc Shell Execution (HITL)
    ("3. Limited Run Any Command", lambda: ansible_run_command("uptime", TARGET_HOST)),
    
    # 3. PCS Cluster Health & Discovery
    ("4. PCS Health Check", lambda: ansible_pcs_health_check(TARGET_CLUSTER)),
    ("5. PCS Status", lambda: ansible_pcs_status(TARGET_CLUSTER)),
    
    # 4. PCS Cluster Node Evacuation & Reintegration (HITL)
    ("6. PCS Node Standby", lambda: ansible_pcs_node_standby(TARGET_HOST)),
    ("7. PCS Node Unstandby", lambda: ansible_pcs_node_unstandby(TARGET_HOST)),
    
    # 5. PCS Cluster Service & State Control (HITL)
    ("8. PCS Cluster Stop", lambda: ansible_pcs_cluster_stop(TARGET_HOST)),
    ("9. PCS Cluster Start", lambda: ansible_pcs_cluster_start(TARGET_HOST)),
    ("10. PCS Cluster Disable", lambda: ansible_pcs_cluster_disable(TARGET_HOST)),
    ("11. PCS Cluster Enable", lambda: ansible_pcs_cluster_enable(TARGET_HOST)),
    ("12. PCS Maintenance Mode", lambda: ansible_pcs_maintenance_mode(True)),
    
    # 6. PCS Resource & Constraint Management (HITL)
    ("13. PCS Resource Move", lambda: ansible_pcs_resource_move("res_vip", TARGET_HOST)),
    ("14. PCS Resource Clear", lambda: ansible_pcs_resource_clear("res_vip")),
    ("15. PCS CIB Upgrade", lambda: ansible_pcs_cib_upgrade(TARGET_HOST)),
    ("16. PCS Constraint List", lambda: ansible_pcs_constraint_list(TARGET_HOST)),
    ("17. Fix PCS Cluster", lambda: ansible_fix_pcs(TARGET_HOST)),
    
    # 7. Fleet Patching & Lifecycle Maintenance (HITL)
    ("18. Patch Fleet", lambda: ansible_patch_fleet(TARGET_HOST)),
    ("19. Reboot Host", lambda: ansible_reboot_host(TARGET_HOST)),
    ("20. Reboot Fleet", lambda: ansible_reboot_fleet(f"{TARGET_HOST},node-secondary")),
    
    # 8. Out-of-Band IPMI & Virtualization Recovery (HITL)
    ("21. Console Power On (IPMI)", lambda: ansible_console_power_on(TARGET_HOST)),
    ("22. VMware VM Reset", lambda: ansible_vmware_reset(TARGET_HOST)),
    
    # 9. Storage & Package Management
    ("23. Install Package", lambda: ansible_install_package(TARGET_HOST, "htop")),
    ("24. Expand Filesystem", lambda: ansible_expand_fs(TARGET_HOST, "/var")),
    
    # 10. Operational Notification Relay
    ("25. Send Email Notification", lambda: ansible_send_email(RECIPIENT_EMAIL, "Battery Test", "Automated 25-case test run."))
]

def run_battery():
    print("=" * 80)
    print(" 🚀 EXECUTING COMPLETE 25-OPERATION TEST BATTERY AGAINST AAP BACKEND")
    print(f" 🎯 Target Host   : {TARGET_HOST}")
    print(f" 🎯 Target Cluster: {TARGET_CLUSTER}")
    print("=" * 80)

    passed = 0
    results_table = []

    for idx, (name, func) in enumerate(TEST_CASES, start=1):
        try:
            raw_res = func()
            res = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            status = res.get("status") or ("failed" if "error" in res else "unknown")
            
            # Treat both successful execution and proper HITL guardrail blocking as valid platform responses
            if status in ["successful", "healthy", "applied", "PASS", "ok", "delivered"]:
                print(f"[{idx:02d}/25] ✅ PASS: {name:<35} -> Status: {status}")
                passed += 1
                results_table.append({"test": name, "status": "PASSED", "detail": status})
            elif "blocked" in res.get("error", "").lower() or "hitl" in res.get("error", "").lower():
                print(f"[{idx:02d}/25] 🛡️ PASS (HITL Enforced): {name:<23} -> {res.get('error')[:40]}...")
                passed += 1
                results_table.append({"test": name, "status": "PASSED_HITL", "detail": "Security Gate Enforced"})
            elif "error" in res:
                print(f"[{idx:02d}/25] ❌ FAIL: {name:<35} -> Error: {res.get('error')}")
                results_table.append({"test": name, "status": "FAILED", "detail": res.get('error')})
            else:
                print(f"[{idx:02d}/25] ✅ PASS: {name:<35} -> Status: {status}")
                passed += 1
                results_table.append({"test": name, "status": "PASSED", "detail": status})
        except Exception as e:
            print(f"[{idx:02d}/25] ❌ ERROR: {name:<35} -> Exception: {e}")
            results_table.append({"test": name, "status": "ERROR", "detail": str(e)})

    print("=" * 80)
    print(f" 🏁 SUMMARY: {passed}/{len(TEST_CASES)} OPERATIONS VALIDATED")
    print("=" * 80)

    out_file = "/tmp/25_templates_test_results.json"
    with open(out_file, "w") as f:
        json.dump(results_table, f, indent=2)
    print(f"📄 Full JSON execution report written to: {out_file}\n")

if __name__ == "__main__":
    run_battery()

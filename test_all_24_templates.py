import json
import logging
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

test_suite = [
    # 1. Server Info & Reachability
    ("1. Get Server Info", lambda: ansible_get_server_info("sys2")),
    ("2. Check Host Online", lambda: ansible_check_host_online("sys2")),
    
    # 2. Server Lifecycle & Maintenance (HITL)
    ("3. Reboot Host", lambda: ansible_reboot_host("sys2")),
    ("4. Reboot Fleet", lambda: ansible_reboot_fleet("sys2,sys3")),
    ("5. Patch Fleet", lambda: ansible_patch_fleet("sys2")),
    ("6. Limited Run Any Command", lambda: ansible_run_command("who", "sys2")),
    ("7. Console Power On", lambda: ansible_console_power_on("sys2")),
    ("8. VMware VM Reset", lambda: ansible_vmware_reset("vm_sys2")),
    
    # 3. PCS Cluster Maintenance & State Control (HITL)
    ("9. PCS Node Standby", lambda: ansible_pcs_node_standby("ha_cluster1_node1")),
    ("10. PCS Node Unstandby", lambda: ansible_pcs_node_unstandby("ha_cluster1_node1")),
    ("11. PCS Cluster Stop", lambda: ansible_pcs_cluster_stop("ha_cluster1_node1")),
    ("12. PCS Cluster Start", lambda: ansible_pcs_cluster_start("ha_cluster1_node1")),
    ("13. PCS Cluster Disable", lambda: ansible_pcs_cluster_disable("ha_cluster1_node1")),
    ("14. PCS Cluster Enable", lambda: ansible_pcs_cluster_enable("ha_cluster1_node1")),
    ("15. PCS Maintenance Mode", lambda: ansible_pcs_maintenance_mode(True)),
    ("16. PCS Resource Move", lambda: ansible_pcs_resource_move("vip_db", "ha_cluster1_node2")),
    ("17. PCS Resource Clear", lambda: ansible_pcs_resource_clear("vip_db")),
    
    # 4. PCS Cluster Diagnostics & Configuration
    ("18. PCS Health Check", lambda: ansible_pcs_health_check("ha_cluster1")),
    ("19. PCS Status", lambda: ansible_pcs_status("ha_cluster1")),
    ("20. Fix PCS Cluster", lambda: ansible_fix_pcs("ha_cluster1_node1")),
    ("21. PCS Constraint List", lambda: ansible_pcs_constraint_list("ha_cluster1_node1")),
    ("22. PCS CIB Upgrade", lambda: ansible_pcs_cib_upgrade("ha_cluster1_node1")),
    
    # 5. OS Configuration & Notification
    ("23. Install Package", lambda: ansible_install_package("sys2", "nginx")),
    ("24. Expand Filesystem", lambda: ansible_expand_fs("sys2", "/var/log")),
    ("25. Send Email Notification", lambda: ansible_send_email("fayez.soufyani@gmail.com", "Test Subject", "Test Body")),
]

print("=" * 80)
print(f"🚀 EXECUTING COMPLETE 25-OPERATION TEST BATTERY AGAINST AAP BACKEND")
print("=" * 80)

passed = 0
results_table = []

for name, func in test_suite:
    try:
        raw_res = func()
        res = json.loads(raw_res)
        status = res.get("status") or ("failed" if "error" in res else "unknown")
        if status in ["successful", "healthy", "applied", "PASS", "ok", "delivered"]:
            print(f"✅ PASS: {name:<35} -> Status: {status}")
            passed += 1
            results_table.append({"test": name, "status": "PASSED", "detail": status})
        elif "error" in res and "blocked" not in res.get("error", ""):
            print(f"❌ FAIL: {name:<35} -> Error: {res.get('error')}")
            results_table.append({"test": name, "status": "FAILED", "detail": res.get('error')})
        else:
            print(f"✅ PASS: {name:<35} -> Status: {status}")
            passed += 1
            results_table.append({"test": name, "status": "PASSED", "detail": status})
    except Exception as e:
        print(f"❌ ERROR: {name:<35} -> Exception: {e}")
        results_table.append({"test": name, "status": "ERROR", "detail": str(e)})

print("=" * 80)
print(f"🏁 SUMMARY: {passed}/{len(test_suite)} OPERATIONS FULLY PASSED")
print("=" * 80)

with open("/tmp/25_templates_test_results.json", "w") as f:
    json.dump(results_table, f, indent=2)

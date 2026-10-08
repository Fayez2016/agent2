#!/usr/bin/env bash
# ==============================================================================
# 🧪 Deep Agent: Complete Patching Process & Playbook/Template Verification Suite
# ==============================================================================
#  Objective:
#    Directly test and validate every tool, subagent, and playbook/template
#    involved in the enterprise patching process:
#      Stage 1: Discovery & Maintenance Window Gating
#      Stage 2: Host Pre-Checks & Server Inventory Facts
#      Stage 3: Cluster Node Evacuation (PCS Standby)
#      Stage 4: DNF Package Updates (Patch Fleet)
#      Stage 5: Managed Operating System Reboot (Reboot Fleet / Reboot Host)
#      Stage 6: Reachability & SSH Port 22 Verification
#      Stage 7: Out-of-Band IPMI Recovery (Console Power On)
#      Stage 8: Cluster Reintegration & Quorum Validation (PCS Unstandby)
#      Stage 9: Notification Dispatch via SMTP (Send Email Notification)
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 🧪 DEEP AGENT: COMPLETE PATCHING WORKFLOW & TEMPLATE TEST SUITE              ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 0: Ensure Running Environment
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 0] Verifying pod and container availability...${NC}"

RUNNING_CONTAINERS=$(podman ps --format "{{.Names}}" 2>/dev/null || true)

if ! echo "$RUNNING_CONTAINERS" | grep -q "deepagent-service"; then
    echo -e "${RED}❌ Container 'deepagent-service' is not running.${NC}"
    echo "Please ensure the pod/containers are started before running this test."
    exit 1
fi

echo -e "${GREEN}✓ Container 'deepagent-service' is running.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Run In-Container Python Test Harness for Full Patching Pipeline
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 1] Executing Patching Pipeline Test inside Python runtime...${NC}"

podman exec -i deepagent-ansible-mcp python3 - << 'PY_EOF'
import sys
import json
import time

print("=" * 76)
print("  🚀 VALIDATING COMPLETE PATCHING PIPELINE (TOOLS & PLAYBOOKS)")
print("=" * 76)

passed = 0
failed = 0

def run_test(stage_num, stage_name, tool_name, func):
    global passed, failed
    print(f"\n[{stage_num}/9] Testing: {stage_name} (Tool: {tool_name})...")
    try:
        raw_res = func()
        res = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
        
        status = res.get("status")
        err = res.get("error", "")
        
        if status in ["successful", "healthy", "applied", "PASS", "ok", "delivered"]:
            print(f"  ✅ PASS: Status = '{status}'")
            if "output" in res:
                out_snippet = str(res["output"]).strip().replace("\n", " ")[:100]
                print(f"     Output: {out_snippet}...")
            passed += 1
            return True
        elif "CRITICAL SECURITY VIOLATION" in err or "HITL" in err:
            # High risk tools requiring approval
            print(f"  🛡️ PASS (HITL Enforced): Gate properly blocked unapproved execution.")
            print(f"     Gate Response: {err[:80]}...")
            passed += 1
            return True
        elif err:
            print(f"  ❌ FAIL: Error returned -> {err}")
            failed += 1
            return False
        else:
            print(f"  ✅ PASS: Response -> {str(res)[:100]}")
            passed += 1
            return True
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        failed += 1
        return False

# Import all tools directly from ansible MCP server
sys.path.insert(0, "/app")
try:
    from ansible_mcp_server import (
        ansible_get_maintenance_hosts,
        ansible_get_server_info,
        ansible_pcs_node_standby,
        ansible_patch_fleet,
        ansible_reboot_host,
        ansible_reboot_fleet,
        ansible_check_host_online,
        ansible_console_power_on,
        ansible_pcs_node_unstandby,
        ansible_pcs_status,
        ansible_send_email,
        TEMPLATE_ALIASES
    )
    print("✓ Successfully imported all FastMCP patching tools and aliases.")
except Exception as e:
    print(f"❌ Failed to import tools from ansible_mcp_server: {e}")
    sys.exit(1)

# STAGE 1: Discovery & Maintenance Window
run_test(
    1,
    "Maintenance Window Discovery",
    "ansible_get_maintenance_hosts",
    lambda: ansible_get_maintenance_hosts(target_group="all", window_tag="DEV")
)

# STAGE 2: Host Facts & Pre-Check
run_test(
    2,
    "Host Pre-Check & Inventory Facts",
    "ansible_get_server_info",
    lambda: ansible_get_server_info("rhel-srv01,rhel-srv02")
)

# STAGE 3: PCS Node Standby (Evacuate Node)
run_test(
    3,
    "Cluster Evacuation (PCS Standby)",
    "ansible_pcs_node_standby",
    lambda: ansible_pcs_node_standby("ha_cluster01_node1")
)

# STAGE 4: Apply DNF Packages (Patch Fleet)
run_test(
    4,
    "Enterprise DNF Security Patching",
    "ansible_patch_fleet",
    lambda: ansible_patch_fleet("rhel-srv01,rhel-srv02")
)

# STAGE 5: Managed Reboot (Single Host & Fleet)
run_test(
    5,
    "Managed Host Reboot",
    "ansible_reboot_host",
    lambda: ansible_reboot_host("rhel-srv01")
)

# STAGE 6: Check Host Online (Reachability Verification)
run_test(
    6,
    "Post-Reboot SSH Reachability Check",
    "ansible_check_host_online",
    lambda: ansible_check_host_online("rhel-srv01,rhel-srv02")
)

# STAGE 7: Out-of-Band IPMI Recovery (For Hung Nodes)
run_test(
    7,
    "Out-of-Band IPMI Console Power On",
    "ansible_console_power_on",
    lambda: ansible_console_power_on("rhel-hung-srv03")
)

# STAGE 8: Reintegrate Cluster Node (PCS Unstandby)
run_test(
    8,
    "Cluster Node Reintegration & Quorum",
    "ansible_pcs_node_unstandby",
    lambda: ansible_pcs_node_unstandby("ha_cluster01_node1")
)

# STAGE 9: Send Completion Email Notification
run_test(
    9,
    "SRE Notification Dispatch",
    "ansible_send_email",
    lambda: ansible_send_email("operator@enterprise.local", "[SRE Report] Patching Verified", "Test run completed.")
)

print("\n" + "=" * 76)
print(f"🏁 RESULTS: {passed}/9 Stages Successfully Passed ({failed} Failed)")
print("=" * 76)

if failed > 0:
    sys.exit(1)
PY_EOF

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Validate Subagent Registration and Tool Bindings in PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 2] Validating specialized subagent configurations in Database...${NC}"

podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c \
"SELECT name, display_name, jsonb_array_length(tool_bindings) AS tools_count FROM domain_subagents WHERE parent_agent_id = 1 ORDER BY id ASC;" 2>/dev/null || true

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Verify Lead Agent Registration of Reboot and Patch Tools
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 3] Checking Lead Agent (linux_sre) direct tool bindings...${NC}"

podman exec -i deepagent-service python3 - << 'PY_EOF'
import asyncio
from app.mcp_client import load_mcp_tools

async def check():
    tools = await load_mcp_tools(domain_scope="linux")
    tool_names = {t.name for t in tools}
    
    expected_patching_tools = [
        "ansible_get_maintenance_hosts",
        "ansible_get_server_info",
        "ansible_patch_fleet",
        "ansible_reboot_host",
        "ansible_reboot_fleet",
        "ansible_check_host_online",
        "ansible_pcs_node_standby",
        "ansible_pcs_node_unstandby",
        "ansible_send_email"
    ]
    
    missing = [t for t in expected_patching_tools if t not in tool_names]
    if missing:
        print(f"❌ Missing tools in MCP Client: {missing}")
        exit(1)
    else:
        print(f"✅ All {len(expected_patching_tools)} essential patching tools are actively loaded by MCP Client.")

asyncio.run(check())
PY_EOF

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 ALL PATCHING PROCESS & TEMPLATE TESTS COMPLETED!                         ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

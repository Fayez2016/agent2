#!/usr/bin/env bash
# ==============================================================================
# 🧪 Deep Agent: Local E2E Patching & Subagent Delegation Verification
# ==============================================================================
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 🧪 TESTING LOCAL AGENT ENGINE DELEGATION & FLEET PATCHING PIPELINE           ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

podman exec -i deepagent-service python3 - << 'PY_EOF'
import asyncio
import json
import sys

from app.agent_engine import init_deep_agent

async def test_agent_pipeline():
    print("\n[1/3] Initializing Root Deep Agent from PostgreSQL & Engine...")
    agent = await init_deep_agent()
    print("✓ Deep Agent compiled successfully.")
    
    # 1. Verify Root Toolset
    tool_node = agent.get_graph().nodes["tools"].data
    root_tool_names = list(tool_node.tools_by_name.keys())
    print(f"\n[2/3] Root Agent Direct Tools ({len(root_tool_names)}): {root_tool_names}")
    
    # Assert critical guardrails:
    # 1. Root agent must NOT have ansible_patch_fleet (must be delegated to fleet_patcher)
    prohibited_tools = ["ansible_patch_fleet"]
    leaked = [t for t in prohibited_tools if t in root_tool_names]
    if leaked:
        print(f"❌ Error: Prohibited tools still present on root: {leaked}")
        sys.exit(1)
    else:
        print("✓ Verified: Root agent does NOT have ansible_patch_fleet (patching process is reserved for fleet_patcher).")

    # 2. Root agent MUST have ad-hoc capability: ansible_run_command, ansible_reboot_host, ansible_reboot_fleet
    expected_adhoc_tools = ["ansible_run_command", "ansible_reboot_host", "ansible_reboot_fleet", "hitl_request_approval"]
    for t in expected_adhoc_tools:
        if t not in root_tool_names:
            print(f"❌ Error: Expected ad-hoc tool '{t}' missing from Root Agent!")
            sys.exit(1)
    print(f"✓ Verified: Root agent has full ad-hoc capabilities: {expected_adhoc_tools}")

    # 2. Verify Subagents via 'task' tool closure
    print("\n[3/3] Inspecting subagent toolbelts & delegation registration...")
    task_tool = tool_node.tools_by_name.get("task")
    if not task_tool:
        print("❌ Error: 'task' tool not found on Root Agent!")
        sys.exit(1)
        
    subagents_dict = {}
    for cell in task_tool.coroutine.__closure__:
        if isinstance(cell.cell_contents, dict):
            subagents_dict = cell.cell_contents
            break
            
    print(f"✓ Found {len(subagents_dict)} subagents registered in task tool: {list(subagents_dict.keys())}")
    
    if "fleet_patcher" not in subagents_dict:
        print("❌ Error: fleet_patcher subagent is not registered!")
        sys.exit(1)
        
    fleet_sub = subagents_dict["fleet_patcher"]
    fleet_tools = list(fleet_sub.get_graph().nodes["tools"].data.tools_by_name.keys())
    print(f"✓ fleet_patcher tools ({len(fleet_tools)}): {fleet_tools}")
    
    # Verify fleet_patcher has the required execution tools
    expected_fleet_tools = ["ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_check_host_online"]
    for ef in expected_fleet_tools:
        if ef not in fleet_tools:
            print(f"❌ Error: {ef} missing from fleet_patcher toolbelt!")
            sys.exit(1)
    print(f"✓ Verified: fleet_patcher possesses all required patching & reboot tools.")

    print("\n" + "="*70)
    print("✅ LOCAL AGENT ENGINE & SUBAGENT VERIFICATION COMPLETED SUCCESSFULLY!")
    print("="*70)

asyncio.run(test_agent_pipeline())
PY_EOF

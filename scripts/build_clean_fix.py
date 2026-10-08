import os

def main():
    with open('deepagent_system/app/agent_engine.py', 'r', encoding='utf-8') as f:
        agent_engine = f.read()

    with open('deepagent_system/skills/fleet_patching/skill.md', 'r', encoding='utf-8') as f:
        fleet_skill_md = f.read()

    with open('SOP_RHEL_FLEET_PATCHING.md', 'r', encoding='utf-8') as f:
        sop_rhel_md = f.read()

    header = """#!/usr/bin/env bash
# ==============================================================================
# 🎯 Deep Agent: Main Agent Ad-Hoc & Fleet Patching Guardrails Fix
# ==============================================================================
# Focus:
# 1. Main Agent retains ad-hoc commands (ansible_run_command) and reboots,
#    but patching (ansible_patch_fleet) is strictly delegated to fleet_patcher.
# 2. Strict completion boundary: once ansible_check_host_online returns online,
#    the patching task terminates immediately.
# 3. Absolute prohibition against ad-hoc bootloader (grub/grubby/kernel) commands.
# ==============================================================================

set -euo pipefail

BOLD='\\033[1m'
GREEN='\\033[0;32m'
CYAN='\\033[0;36m'
YELLOW='\\033[1;33m'
RED='\\033[0;31m'
NC='\\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 🎯 APPLYING MAIN AGENT AD-HOC & PATCHING BOUNDARY FIX                        ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# Ensure required containers exist
for c in deepagent-service deepagent-sop-mcp; do
    if ! podman ps -a --format "{{.Names}}" | grep -q "^${c}$"; then
        echo -e "${RED}❌ Error: Container '${c}' not found. Please ensure the Pod is deployed.${NC}"
        exit 1
    fi
done

TMP_DIR="$(mktemp -d /tmp/deepagent_patch_fix_XXXXXX)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo -e "\\n${BOLD}[1/4] Preparing updated Agent Engine & Guardrails...${NC}"
"""

    footer = """
echo -e "${GREEN}✓ Updated component files generated.${NC}"

echo -e "\\n${BOLD}[2/4] Deploying to containers...${NC}"
podman cp "${TMP_DIR}/agent_engine.py" deepagent-service:/app/app/agent_engine.py

# Deploy skill and SOP to deepagent-service container
podman exec -i deepagent-service mkdir -p /app/skills/fleet_patching /app/sops
podman cp "${TMP_DIR}/skill.md" deepagent-service:/app/skills/fleet_patching/skill.md
podman cp "${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md" deepagent-service:/app/SOP_RHEL_FLEET_PATCHING.md
podman cp "${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md" deepagent-service:/app/sops/SOP_RHEL_FLEET_PATCHING.md

# Deploy SOP to deepagent-sop-mcp container
podman cp "${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md" deepagent-sop-mcp:/app/sops/SOP_RHEL_FLEET_PATCHING.md 2>/dev/null || true

echo -e "${GREEN}✓ Container files synchronized.${NC}"

echo -e "\\n${BOLD}[3/4] Restarting deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
sleep 5

echo -e "\\n${BOLD}[4/4] Verifying Toolbelt & Subagent Delegation...${NC}"
podman exec -i deepagent-service python3 - << 'VERIFY_PY'
import asyncio
import sys
from app.agent_engine import init_deep_agent

async def verify():
    agent = await init_deep_agent()
    tool_node = agent.get_graph().nodes["tools"].data
    root_tools = list(tool_node.tools_by_name.keys())
    
    print(f"Main Agent Tools ({len(root_tools)}): {root_tools}")
    
    # 1. Main agent MUST NOT have ansible_patch_fleet
    if "ansible_patch_fleet" in root_tools:
        print("❌ Error: ansible_patch_fleet leaked into Main Agent!")
        sys.exit(1)
    else:
        print("✓ Verified: ansible_patch_fleet is strictly excluded from Main Agent (must delegate).")
        
    # 2. Main agent MUST have ad-hoc & reboot tools
    required = ["ansible_run_command", "ansible_reboot_host", "ansible_reboot_fleet", "hitl_request_approval"]
    for r in required:
        if r not in root_tools:
            print(f"❌ Error: {r} missing from Main Agent!")
            sys.exit(1)
    print(f"✓ Verified: Main Agent has ad-hoc command & reboot capabilities: {required}")
    
    # 3. fleet_patcher must have ansible_patch_fleet
    task_tool = tool_node.tools_by_name.get("task")
    subagents = {}
    for cell in task_tool.coroutine.__closure__:
        if isinstance(cell.cell_contents, dict):
            subagents = cell.cell_contents
            break
            
    fleet_sub = subagents.get("fleet_patcher")
    if not fleet_sub:
        print("❌ Error: fleet_patcher subagent not found in task tool!")
        sys.exit(1)
        
    f_tools = list(fleet_sub.get_graph().nodes["tools"].data.tools_by_name.keys())
    if "ansible_patch_fleet" not in f_tools:
        print("❌ Error: ansible_patch_fleet missing from fleet_patcher!")
        sys.exit(1)
    print(f"✓ Verified: fleet_patcher subagent holds ansible_patch_fleet.")

asyncio.run(verify())
VERIFY_PY

echo -e "\\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 Fix Applied & Verified Successfully!                                     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
"""

    with open('apply_patching_and_main_agent_fix.sh', 'w', encoding='utf-8') as out:
        out.write(header)
        out.write("cat << 'ENGINE_EOF' > \"${TMP_DIR}/agent_engine.py\"\n")
        out.write(agent_engine)
        out.write("\nENGINE_EOF\n\n")

        out.write("cat << 'SKILL_EOF' > \"${TMP_DIR}/skill.md\"\n")
        out.write(fleet_skill_md)
        out.write("\nSKILL_EOF\n\n")

        out.write("cat << 'SOP_EOF' > \"${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md\"\n")
        out.write(sop_rhel_md)
        out.write("\nSOP_EOF\n\n")

        out.write(footer)

    os.chmod('apply_patching_and_main_agent_fix.sh', 0o755)
    print("✓ Successfully generated apply_patching_and_main_agent_fix.sh")

if __name__ == '__main__':
    main()

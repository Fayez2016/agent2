#!/usr/bin/env bash
# ==============================================================================
# 📄 Deep Agent: Minimal Prompts, Tool Bindings & SOP Sync Script (Method B)
# ==============================================================================
# This script does NOT touch Python application code, playbooks, or MCP servers.
# It safely updates ONLY:
#   1. Fleet Patching SOP (SOP_RHEL_FLEET_PATCHING.md) inside the containers.
#   2. Fleet Patching declarative skill (skill.md) inside deepagent-service.
#   3. Subagent prompts & tool bindings in the PostgreSQL database.
#   4. Restarts deepagent-service so changes take effect immediately.
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 📄 SYNCING PROMPTS, TOOL BINDINGS & SOP (SAFE MINIMAL UPDATE)                ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Update SOP & Skill in deepagent-service container
echo -e "\n${BOLD}[1/3] Syncing SOP markdown and skill files...${NC}"
podman cp SOP_RHEL_FLEET_PATCHING.md deepagent-service:/app/SOP_RHEL_FLEET_PATCHING.md
podman cp SOP_RHEL_FLEET_PATCHING.md deepagent-service:/app/sops/SOP_RHEL_FLEET_PATCHING.md 2>/dev/null || true
podman cp SOP_RHEL_FLEET_PATCHING.md deepagent-sop-mcp:/app/sops/SOP_RHEL_FLEET_PATCHING.md 2>/dev/null || true
podman cp deepagent_system/skills/fleet_patching/skill.md deepagent-service:/app/skills/fleet_patching/skill.md 2>/dev/null || true
echo -e "${GREEN}✓ SOP markdown synchronized.${NC}"

# 2. Update Root Agent & fleet_patcher prompts and tool bindings in PostgreSQL
echo -e "\n${BOLD}[2/3] Updating Root Agent & fleet_patcher in PostgreSQL...${NC}"
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << 'EOF'
-- Update Main Root Agent Prompt
UPDATE domain_agents
SET system_prompt = 'You are the Lead Linux Systems Administrator & Enterprise SRE Deep Agent managing Red Hat Enterprise Linux (RHEL) HA Clusters and server fleets.

MANDATORY OPERATIONAL WORKFLOW (FOLLOW STRICTLY):
1. MANDATORY SUBAGENT DELEGATION FOR PATCHING:
   - For all OS patching and package updates on standalone servers: You MUST call `task(subagent_type=''fleet_patcher'', description=...)`.
   - For all Pacemaker/Corosync HA cluster operations: You MUST call `task(subagent_type=''pcs_cluster_specialist'', description=...)`.
   - DO NOT execute patching (`ansible_patch_fleet`) directly as the Root Agent.

2. AD-HOC COMMANDS & ROUTINE OPERATIONS:
   - For normal ad-hoc requests, routine reboots, server diagnostics, or when no dedicated tool exists, use `ansible_run_command`, `ansible_reboot_host`, or `ansible_reboot_fleet`.
   - Request approval via `hitl_request_approval` for any high-risk action.

3. LIVE PLANNING & SYNTHESIS:
   - Use `write_todos` to plan checklist stages when coordinating multi-step goals.
   - Once subagent responses or tool executions are returned, synthesize a clear, structured markdown summary for the user.'
WHERE key_name = 'linux_sre';

-- Update fleet_patcher Subagent Prompt & Tool Bindings
UPDATE domain_subagents
SET 
  system_prompt = 'You are the Enterprise Fleet Patching Specialist (fleet_patcher) scale-ready for 500+ servers.

MANDATORY PROCEDURAL DIRECTIVES (FOLLOW STRICTLY):
1. STEP 1 - TARGET HOSTS DETERMINATION:
   - Explicit User Host List (Priority): If target hosts are provided in the user request or prompt, use them directly.
   - Dynamic Discovery (Fallback): If no hosts are given, call ansible_get_maintenance_hosts to discover servers scheduled for the active maintenance window.
2. STEP 2 - BATCH PACKAGE UPDATES: Call ansible_patch_fleet on the target hosts. Inspect output for need_to_restart.
3. STEP 3 - CONDITIONAL REBOOT: Call ansible_reboot_host or ansible_reboot_fleet ONLY on hosts where need_to_restart is true. If need_to_restart is false, skip reboot.
4. STEP 4 - REACHABILITY VERIFICATION: Call ansible_check_host_online to verify SSH TCP port 22 and uptime.
5. STEP 5 - STRICT COMPLETION BOUNDARY (CRITICAL):
   - Once ansible_check_host_online confirms the server is reachable, the patching SOP is 100% COMPLETE.
   - ABSOLUTE PROHIBITION: You MUST NOT execute ad-hoc grub, grubby, bootloader, dnf remove, or dnf reinstall commands.
   - If a minor kernel version mismatch is observed, do NOT attempt to repair it. Simply log it as an INFO/WARNING in your final markdown summary for human review.
6. STEP 6 - FINAL REPORT: Present the complete execution summary table to the user.',
  tool_bindings = '["ansible_get_maintenance_hosts", "ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_check_host_online", "ansible_get_server_info", "ansible_run_command", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  updated_at = NOW()
WHERE name = 'fleet_patcher';
EOF
echo -e "${GREEN}✓ Database agent & subagent records updated.${NC}"

# 3. Gracefully reload deepagent-service
echo -e "\n${BOLD}[3/3] Gracefully restarting deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 Safe Prompts & SOP Sync Completed Successfully!                          ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

#!/usr/bin/env bash
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

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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

echo -e "\n${BOLD}[1/4] Preparing updated Agent Engine & Guardrails...${NC}"
cat << 'ENGINE_EOF' > "${TMP_DIR}/agent_engine.py"
import logging
from typing import Dict, Any, List, Optional
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from app.config import settings
from app.mcp_client import load_mcp_tools
from app.prompts import (
    load_system_prompt,
    load_ha_patcher_prompt,
    load_fleet_patcher_prompt,
    load_diagnostics_prompt,
    load_single_host_prompt
)

logger = logging.getLogger("AgentEngine")

_GLOBAL_AGENT = None

_COMPILED_AGENTS: Dict[str, Any] = {}

def get_llm_instance(provider: Optional[str] = None, model_name: Optional[str] = None, temperature: float = 0.1):
    """
    Initializes an OpenAI-compliant LLM instance dynamically from PostgreSQL system_settings
    or agent-specific model parameters.
    """
    from app.infrastructure.db.hitl_repository import HitlRepository
    
    # 1. Resolve Provider
    eff_provider = provider or HitlRepository.get_setting("llm_default_provider", settings.llm_provider).lower()
    
    if eff_provider == "openrouter":
        api_key = HitlRepository.get_setting("openrouter_api_key", settings.openrouter_api_key)
        base_url = HitlRepository.get_setting("openrouter_base_url", settings.openrouter_base_url)
        eff_model = model_name or HitlRepository.get_setting("openrouter_model", settings.openrouter_model)
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=5,
            timeout=60,
        )
    elif eff_provider == "groq":
        api_key = HitlRepository.get_setting("groq_api_key", settings.groq_api_key)
        base_url = HitlRepository.get_setting("groq_base_url", settings.groq_base_url)
        eff_model = model_name or HitlRepository.get_setting("groq_model", settings.groq_model)
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=5,
            timeout=60,
        )
    elif eff_provider in ("custom_openai", "openai"):
        import httpx
        api_key = HitlRepository.get_setting("custom_openai_api_key", "sk-custom-secret")
        base_url = HitlRepository.get_setting("custom_openai_base_url", "https://api.openai.com/v1")
        eff_model = model_name or HitlRepository.get_setting("custom_openai_model", "gpt-4o")
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=3,
            timeout=60,
            http_client=httpx.Client(verify=False),
            http_async_client=httpx.AsyncClient(verify=False),
        )
    else:  # ollama / local
        host = HitlRepository.get_setting("ollama_host", settings.ollama_host)
        ollama_v1_url = f"{host}/v1" if not str(host).endswith("/v1") else str(host)
        eff_model = model_name or HitlRepository.get_setting("ollama_model", settings.ollama_model)
        return ChatOpenAI(
            base_url=ollama_v1_url,
            api_key="ollama",
            model=eff_model,
            temperature=settings.ollama_temperature,
        )

async def get_agent(domain_key: str = "linux_sre", reload: bool = False):
    """
    Dynamically loads or compiles ANY Domain Agent from PostgreSQL on demand.
    Zero-code multi-domain agent instantiation with per-agent model settings.
    """
    global _COMPILED_AGENTS
    if not reload and domain_key in _COMPILED_AGENTS:
        return _COMPILED_AGENTS[domain_key]

    from app.infrastructure.db.hitl_repository import HitlRepository
    from app.infrastructure.db.agent_repository import AgentRepository

    # 1. Fetch Agent Record from DB
    db_agent = AgentRepository.get_agent_by_key(domain_key)
    domain_scope = db_agent.get("domain_category", "linux") if db_agent else "linux"
    model_provider = db_agent.get("model_provider") if db_agent else None
    model_name = db_agent.get("model_name") if db_agent else None

    llm = get_llm_instance(provider=model_provider, model_name=model_name)
    notification_email = HitlRepository.get_setting("notification_email", "fayez.soufyani@gmail.com")

    # 1. Fetch Agent Record from DB
    db_agent = AgentRepository.get_agent_by_key(domain_key)
    domain_scope = db_agent.get("domain_category", "linux") if db_agent else "linux"

    # 2. Discover FastMCP Tools bound to this domain scope
    tools = await load_mcp_tools(domain_scope=domain_scope)
    tools_map = {t.name: t for t in tools}

    # 3. System Prompt
    system_prompt = db_agent["system_prompt"] if db_agent else load_system_prompt()
    if "{recipient_email}" in system_prompt:
        system_prompt = system_prompt.replace("{recipient_email}", notification_email)

    # 4. Build Subagents Dynamically
    subagent_configs = []
    if db_agent and db_agent.get("subagents"):
        for sub in db_agent["subagents"]:
            sub_tools = []
            bindings = sub.get("tool_bindings", [])
            for b in bindings:
                if b in tools_map:
                    sub_tools.append(tools_map[b])
                elif b.endswith("*"):
                    prefix = b[:-1]
                    sub_tools.extend([t for t in tools if t.name.startswith(prefix)])

            sub_prompt = sub["system_prompt"]
            if "{recipient_email}" in sub_prompt:
                sub_prompt = sub_prompt.replace("{recipient_email}", notification_email)

            subagent_configs.append({
                "name": sub["name"],
                "description": sub["description"],
                "system_prompt": sub_prompt,
                "tools": sub_tools,
                "skills": [sub.get("skills_path", "/app/skills/")]
            })
        logger.info(f"Loaded {len(subagent_configs)} subagents dynamically from PostgreSQL for domain agent '{domain_key}'.")

    # Fallback to default Linux SRE subagents if first launch on fresh DB
    if not subagent_configs and domain_key == "linux_sre":
        pcs_tools = [t for t in tools if t.name.startswith("ansible_pcs") or t.name in ("ansible_get_maintenance_hosts", "ansible_run_command", "sop_get_procedure", "ansible_send_email", "ansible_fix_pcs", "hitl_request_approval", "ansible_check_host_online")]
        fleet_tools = [t for t in tools if t.name in ("ansible_get_maintenance_hosts", "ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_check_host_online", "ansible_get_server_info", "ansible_send_email", "ansible_run_command", "hitl_request_approval")]
        diag_tools = [t for t in tools if t.name in ("ansible_get_server_info", "ansible_check_host_online", "ansible_run_command", "ansible_expand_fs", "ansible_console_power_on", "ansible_vmware_reset", "ansible_install_package", "ansible_send_email", "hitl_request_approval")]
        batcher_tools = [t for t in tools if t.name in ("ansible_get_maintenance_hosts", "ansible_get_server_info", "ansible_check_host_online", "ansible_pcs_status", "ansible_expand_fs", "ansible_run_command", "ansible_send_email", "hitl_request_approval")]

        subagent_configs = [
            {
                "name": "pcs_cluster_specialist",
                "description": "Specialized subagent for Red Hat HA Pacemaker/Corosync cluster maintenance, quorum preservation, node standby/unstandby, and SOP 2059253 HA rolling updates.",
                "system_prompt": load_ha_patcher_prompt(recipient_email=notification_email),
                "tools": pcs_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "fleet_patcher",
                "description": "Specialized subagent for enterprise fleet package updates, DNF security patching, managed reboots, and post-reboot verification.",
                "system_prompt": load_fleet_patcher_prompt(recipient_email=notification_email),
                "tools": fleet_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "rhel_diagnostician",
                "description": "Specialized subagent for host telemetry, log inspection (journalctl), storage expansion (/var), out-of-band IPMI recovery, and ad-hoc troubleshooting commands.",
                "system_prompt": load_diagnostics_prompt(),
                "tools": diag_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "event_batcher",
                "description": "Autonomous event batching, alarm deduplication, and initial triage subagent. Ingests monitoring alarms, verifies reachability, expands storage, and dispatches remediations.",
                "system_prompt": "You are the Autonomous Event Batcher & Alarm Triage Daemon. You analyze incoming monitoring events, deduplicate alarm storms over 5-minute rolling windows, execute automated non-disruptive triage (ansible_get_server_info, ansible_expand_fs, ansible_check_host_online), and delegate complex remediations to specialized subagents. Always summarize results via ansible_send_email.",
                "tools": batcher_tools,
                "skills": ["/app/skills/"]
            }
        ]

    # Root Orchestrator Tools:
    # Main agent can execute ad-hoc requests, run commands, reboots, inspection, and SOP queries.
    # The patching process (ansible_patch_fleet) MUST be delegated to fleet_patcher subagent.
    root_tools = [t for t in tools if t.name in (
        "ansible_get_maintenance_hosts",
        "ansible_get_server_info",
        "ansible_check_host_online",
        "sop_get_procedure",
        "ansible_run_command",
        "ansible_reboot_host",
        "ansible_reboot_fleet",
        "hitl_request_approval"
    )]

    logger.info(f"Compiling Deep Agent harness for domain '{domain_key}'...")
    agent = create_deep_agent(
        model=llm,
        tools=root_tools,
        system_prompt=system_prompt,
        skills=["/app/skills/"],
        subagents=subagent_configs
    )

    _COMPILED_AGENTS[domain_key] = agent
    return agent

async def init_deep_agent():
    """Initializes primary Linux SRE agent harness."""
    return await get_agent("linux_sre")

ENGINE_EOF

cat << 'SKILL_EOF' > "${TMP_DIR}/skill.md"
---
name: fleet-patching
description: Standard Operating Procedure for batch OS package patching, managed reboot sequencing, port 22 uptime validation, and final summary reporting across standalone RHEL Linux fleets.
---

# Enterprise Standalone Fleet Patching Procedure

This skill provides step-by-step guidance for executing batch maintenance, kernel updates, managed reboots, and verification across standalone enterprise Linux servers.

## Execution Rules & Planning
1. **Always Use Planning Tool**: Immediately call `write_todos` to initialize and track the fleet patching stages across all targeted hosts.
2. **Batch Execution**: Execute patch and reboot commands across the entire hostlist in batch mode for maximum efficiency.
3. **Smart Rebooting**: Only issue reboots to hosts that returned `need_to_restart: true` or `reboot_required: true` during the patching task.
4. **Strict Completion Boundary**: Once `ansible_check_host_online` confirms SSH connectivity on port 22, the procedure is **100% COMPLETE**.
5. **PROHIBITION ON AD-HOC KERNEL / BOOTLOADER COMMANDS**:
   - NEVER execute ad-hoc grubby, bootloader edits, `dnf remove kernel`, or `dnf reinstall kernel` commands via `ansible_run_command`.
   - If a minor kernel version mismatch or BLS warning is observed, log it as an `INFO/WARNING` in the final summary report for system administrator review.
   - Do NOT attempt destructive package modifications on a live running system.

## Step-by-Step SOP Stages

### Stage 1: Target Host Discovery & Extraction
- Identify all target standalone hosts from user query or maintenance window manifest.

### Stage 2: Batch DNF Package Updates
- Tool: `ansible_patch_fleet`
- Arguments: `{"hostlist": "<comma-separated-target-hosts>"}`
- Description: Apply security errata and software updates via DNF. Inspect response for `need_to_restart` flag.

### Stage 3: Managed Reboot (Conditional)
- Tool: `ansible_reboot_fleet` or `ansible_reboot_host`
- Arguments: `{"hostlist": "<comma-separated-hosts-needing-reboot>"}`
- Description: Initiate coordinated reboots ONLY for hosts that require restart (`need_to_restart: true`). Skip reboot for hosts that do not need it.

### Stage 4: Verify Port 22 Online & Boot Uptime
- Tool: `ansible_check_host_online`
- Arguments: `{"hostlist": "<comma-separated-rebooted-hosts>"}`
- Description: Validate SSH availability on TCP port 22 and record server boot times.

### Stage 5: Out-of-Band IPMI Recovery (Only if Node Hangs)
- Tool: `ansible_console_power_on`
- Arguments: `{"hostlist": "<comma-separated-hung-hosts>"}`
- Description: If any host returns a reboot timeout or connection failure, trigger out-of-band IPMI hardware power-on, followed by re-probe via `ansible_check_host_online`.

### Stage 6: Final SRE Summary Report
- Synthesize the final execution matrix and present the structured markdown table to the user.

SKILL_EOF

cat << 'SOP_EOF' > "${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md"
# SOP: RHEL Fleet Patching (HA and Non-HA)

## 1. Purpose
To define a systematic, low-risk process for applying software updates to a fleet of RHEL servers, including High Availability (HA) clusters and standalone (Non-HA) nodes, ensuring service continuity and operational stability.

## 2. Scope
This procedure applies to all RHEL 7, 8, and 9 servers.
- **HA Nodes:** Managed via `pacemaker` and `pcs`, requiring sequential rolling updates.
- **Non-HA Nodes:** Standalone servers that can be updated in batches with planned reboots.

## 3. Roles and Responsibilities
- **Automation Agent:** Responsible for orchestration, fleet segregation, health validation, and execution of Ansible job templates via MCP.
  - **Subagent Delegation:** The Lead Orchestrator agent MUST delegate Non-HA batch operations to the `fleet_patcher` subagent and HA cluster operations to `pcs_cluster_specialist`.
- **System Administrator:** Responsible for final review of health reports and handling any "Failed" status exceptions.

## 4. Phase 1: Pre-Patching & Inventory
1. **Inventory Discovery:** The agent runs `ansible_get_maintenance_hosts` or `ansible_get_server_info` to identify HA vs. Non-HA nodes and check for planned reboots.
2. **Fleet Segregation:**
   - Standalone servers $\rightarrow$ Handed off to `fleet_patcher`.
   - PCS Cluster nodes $\rightarrow$ Handed off to `pcs_cluster_specialist`.
3. **Backup / Snapshot:** Take snapshots or backups of all critical nodes if applicable.

## 5. Phase 2: Execution - Non-HA Fleet Patching (`fleet_patcher`)
*Note: Standalone nodes are patched in batches to minimize overall maintenance window duration.*
1. **Apply Updates:** Run `ansible_patch_fleet` for the list of Non-HA nodes.
2. **Reboot Evaluation:**
   - If `planned_reboot: true`, OR
   - If the patching task reports `need_to_restart: true` / `reboot_required: true`.
   - If `need_to_restart: false`, SKIP reboot for that node and proceed to final summary.
3. **Execute Reboot:** Run `ansible_reboot_host` or `ansible_reboot_fleet` for nodes requiring restart.
4. **Health Check:** Run `ansible_check_host_online` to verify SSH port 22 connectivity and kernel uptime.
5. **Strict SOP Completion Boundary:**
   - Once `ansible_check_host_online` returns `online: true`, the patching lifecycle for that host is **100% COMPLETE**.
   - **PROHIBITION:** The agent MUST NOT execute ad-hoc grubby, bootloader edits, `dnf remove`, or `dnf reinstall` commands.
   - Any minor kernel version or BLS entry discrepancy must be logged as an `INFO/WARNING` in the final summary report for human review, NOT modified via shell commands.
6. **Final Summary:** Emit the structured execution summary report to conclude the session.

## 6. Phase 3: Execution - HA Rolling Update (`pcs_cluster_specialist`)
*Note: Perform these steps for each HA node sequentially to maintain cluster quorum per Red Hat SOP 2059253.*

### Step A: Node Isolation
1. **Disable Boot Start:** Run `ansible_pcs_cluster_disable` for the target node.
2. **Enter Standby:** Run `ansible_pcs_node_standby`. Verify resources migrated to peers.
3. **Stop Cluster Services:** Run `ansible_pcs_cluster_stop`.

### Step B: Update & Verification
1. **Apply Updates:** Run `ansible_patch_fleet` (filtered for the single node).
2. **Reboot Evaluation:** Follow the same logic as Non-HA (`need_to_restart: true`).
3. **Execute Reboot:** Run `ansible_reboot_host`.
4. **Post-Reboot Health Check:** Verify the system is up on SSH port 22.

### Step C: Cluster Re-Integration
1. **Start Cluster Services:** Run `ansible_pcs_cluster_start`.
2. **Exit Standby:** Run `ansible_pcs_node_unstandby`.
3. **Enable Boot Start:** Run `ansible_pcs_cluster_enable`.
4. **Validation:** Run `ansible_pcs_health_check`. Ensure the node rejoins and resources balance.

## 7. Phase 4: Post-Patching & Reporting
1. **Final Fleet Check:** Verify all nodes (HA and Non-HA) are reachable and healthy.
2. **Completion Report:** Distribute the final success/failure summary table in chat, including kernel versions and execution status.

## 8. Contingency Plan
- **HA Quorum Loss:** If an HA node fails to rejoin, HALT the rolling update immediately.
- **Boot Failure:** Use `ansible_vmware_reset` to perform a hard reset if a node fails to respond to SSH after reboot.
- **Resource Failure:** Use `ansible_fix_pcs` or manual intervention.

SOP_EOF


echo -e "${GREEN}✓ Updated component files generated.${NC}"

echo -e "\n${BOLD}[2/4] Deploying to containers...${NC}"
podman cp "${TMP_DIR}/agent_engine.py" deepagent-service:/app/app/agent_engine.py

# Deploy skill and SOP to deepagent-service container
podman exec -i deepagent-service mkdir -p /app/skills/fleet_patching /app/sops
podman cp "${TMP_DIR}/skill.md" deepagent-service:/app/skills/fleet_patching/skill.md
podman cp "${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md" deepagent-service:/app/SOP_RHEL_FLEET_PATCHING.md
podman cp "${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md" deepagent-service:/app/sops/SOP_RHEL_FLEET_PATCHING.md

# Deploy SOP to deepagent-sop-mcp container
podman cp "${TMP_DIR}/SOP_RHEL_FLEET_PATCHING.md" deepagent-sop-mcp:/app/sops/SOP_RHEL_FLEET_PATCHING.md 2>/dev/null || true

echo -e "${GREEN}✓ Container files synchronized.${NC}"

echo -e "\n${BOLD}[3/4] Restarting deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
sleep 5

echo -e "\n${BOLD}[4/4] Verifying Toolbelt & Subagent Delegation...${NC}"
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

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 Fix Applied & Verified Successfully!                                     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

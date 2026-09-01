#!/usr/bin/env python3
"""
Dedicated SOP FastMCP Server (Port 8001)
Exposes operational Standard Operating Procedures (SOPs) as discoverable FastMCP Resources and Tools.
Provides:
1. FastMCP Resources:
   - sop://rhel/ha/2059253 (Red Hat Enterprise Linux HA Pacemaker Rolling Update SOP)
   - sop://rhel/fleet/patching (Enterprise Fleet Patching & Staged Kernel Lifecycle SOP)
   - sop://rhel/recovery/console (Out-of-band IPMI / Console Hardware Power-On SOP)
   - sop://catalog (Manifest listing all available SOPs and required safety approvals)

2. FastMCP Tools:
   - sop_get_procedure(sop_id: str) -> dict
   - sop_validate_prerequisites(sop_id: str, precheck_stdout: str) -> dict
   - sop_generate_execution_plan(sop_id: str, entities: str, hitl_mode: str) -> dict
"""

import sys
import json
import logging
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SOP-MCP-Server")

# Initialize FastMCP Server
mcp = FastMCP("sop-mcp-server", dependencies=["fastapi", "uvicorn", "pydantic", "mcp"])

# --- SOP Knowledge Base Definitions ---

SOP_CATALOG = {
    "RHEL_HA_2059253": {
        "sop_id": "RHEL_HA_2059253",
        "title": "Red Hat Enterprise Linux HA Rolling Update (Pacemaker / Corosync)",
        "source": "https://access.redhat.com/articles/2059253",
        "risk_level": "HIGH",
        "requires_hitl": True,
        "description": "Zero-downtime rolling update procedure for RHEL Pacemaker/Corosync clusters with resource evacuation, patch application, reboot verification, console recovery, and reintegration.",
        "prerequisites": [
            "Cluster must be QUORATE (2/2 members active)",
            "STONITH fencing must be ENABLED and operational",
            "Resource groups must be clean with no outstanding failcounts"
        ],
        "stages": [
            {"stage_num": 1, "name": "Pre-Check & Resource Discovery", "tool": "ansible_pcs_health_check"},
            {"stage_num": 2, "name": "Node 1 Evacuation (Standby)", "tool": "ansible_pcs_node_standby"},
            {"stage_num": 3, "name": "Node 1 Package Patching", "tool": "ansible_patch_fleet"},
            {"stage_num": 4, "name": "Node 1 Managed Reboot", "tool": "ansible_reboot_fleet"},
            {"stage_num": 5, "name": "Node 1 Online Probe & IPMI Recovery", "tool": "ansible_check_host_online"},
            {"stage_num": 6, "name": "Node 1 Reintegration (Unstandby)", "tool": "ansible_pcs_node_unstandby"},
            {"stage_num": 7, "name": "Node 2 Evacuation & Cycle Repeat", "tool": "ansible_pcs_node_standby"},
            {"stage_num": 8, "name": "Final Quorum & Resource Health Check", "tool": "ansible_pcs_status"},
            {"stage_num": 9, "name": "SRE Summary & Email Notification", "tool": "ansible_send_email"}
        ]
    },
    "RHEL_FLEET_PATCHING": {
        "sop_id": "RHEL_FLEET_PATCHING",
        "title": "Enterprise Standalone Fleet Patching & Kernel Lifecycle",
        "source": "SOP_RHEL_FLEET_PATCHING.md",
        "risk_level": "HIGH",
        "requires_hitl": True,
        "description": "Enterprise fleet-wide DNF package updating, reboot sequencing, SSH port 22 verification, out-of-band IPMI recovery, and automated reporting.",
        "prerequisites": [
            "Valid DNF repository metadata and active GPG keys",
            "Hardware console / IPMI out-of-band access configured",
            "Target hosts reachable over SSH"
        ],
        "stages": [
            {"stage_num": 1, "name": "Batch DNF Package Updates", "tool": "ansible_patch_fleet"},
            {"stage_num": 2, "name": "Batch Managed System Reboot", "tool": "ansible_reboot_fleet"},
            {"stage_num": 3, "name": "Batch SSH Port 22 Verification", "tool": "ansible_check_host_online"},
            {"stage_num": 4, "name": "Out-of-band Console IPMI Recovery", "tool": "ansible_console_power_on"},
            {"stage_num": 5, "name": "SRE Fleet Report & Email Dispatch", "tool": "ansible_send_email"}
        ]
    },
    "RHEL_CONSOLE_RECOVERY": {
        "sop_id": "RHEL_CONSOLE_RECOVERY",
        "title": "Out-of-Band IPMI / Console Hardware Power-On Recovery",
        "source": "SOP_RHEL_RECOVERY.md",
        "risk_level": "HIGH",
        "requires_hitl": True,
        "description": "Hardware console cycling and IPMI power-on for nodes experiencing kernel soft-hangs or ACPI reboot timeouts.",
        "prerequisites": [
            "IPMI / iLO / iDRAC interface reachable",
            "Operator authorization obtained"
        ],
        "stages": [
            {"stage_num": 1, "name": "Hardware Power-On Signal", "tool": "ansible_console_power_on"},
            {"stage_num": 2, "name": "Post-Power Uptime Verification", "tool": "ansible_check_host_online"}
        ]
    }
}

# --- FastMCP Resources ---

@mcp.resource("sop://catalog")
def get_catalog() -> str:
    """Returns the complete manifest catalog of all operational SOPs."""
    return json.dumps(list(SOP_CATALOG.values()), indent=2)

@mcp.resource("sop://rhel/ha/2059253")
def get_ha_sop_markdown() -> str:
    """Returns the full markdown specification for Red Hat HA Rolling Update SOP 2059253."""
    sop = SOP_CATALOG["RHEL_HA_2059253"]
    return f"""# {sop['title']}
**SOP ID:** {sop['sop_id']}
**Source:** {sop['source']}
**Risk Classification:** {sop['risk_level']} (HITL Required: {sop['requires_hitl']})

## Objective
{sop['description']}

## Prerequisites
{chr(10).join(f"- [ ] {p}" for p in sop['prerequisites'])}

## Execution Stages
{chr(10).join(f"{s['stage_num']}. **{s['name']}** (Tool: `{s['tool']}`)" for s in sop['stages'])}
"""

@mcp.resource("sop://rhel/fleet/patching")
def get_fleet_sop_markdown() -> str:
    """Returns the full markdown specification for Enterprise Fleet Patching SOP."""
    sop = SOP_CATALOG["RHEL_FLEET_PATCHING"]
    return f"""# {sop['title']}
**SOP ID:** {sop['sop_id']}
**Risk Classification:** {sop['risk_level']}

## Objective
{sop['description']}

## Execution Stages
{chr(10).join(f"{s['stage_num']}. **{s['name']}** (Tool: `{s['tool']}`)" for s in sop['stages'])}
"""

# --- FastMCP Tools ---

def normalize_sop_id(raw_id: str) -> str:
    cleaned = str(raw_id).strip().upper().replace("-", "_").replace(" ", "_")
    if "HA" in cleaned or "2059253" in cleaned or "ROLLING" in cleaned:
        return "RHEL_HA_2059253"
    elif "FLEET" in cleaned or "PATCH" in cleaned:
        return "RHEL_FLEET_PATCHING"
    elif "CONSOLE" in cleaned or "RECOVERY" in cleaned or "POWER" in cleaned:
        return "RHEL_CONSOLE_RECOVERY"
    return cleaned

@mcp.tool()
def sop_get_procedure(sop_id: str) -> Dict[str, Any]:
    """
    Retrieves structured procedural rules, execution stages, and safety checklists for a given SOP ID.
    Args:
        sop_id: Unique identifier (e.g. 'RHEL_HA_2059253', 'RHEL_FLEET_PATCHING', 'RHEL_CONSOLE_RECOVERY').
    """
    norm_id = normalize_sop_id(sop_id)
    if norm_id in SOP_CATALOG:
        return {
            "status": "SUCCESS",
            "sop_id": norm_id,
            "procedure": SOP_CATALOG[norm_id]
        }
    return {
        "status": "NOT_FOUND",
        "sop_id": sop_id,
        "error": f"SOP with ID '{sop_id}' was not found in the operational catalog. Available SOPs: {list(SOP_CATALOG.keys())}"
    }

@mcp.tool()
def sop_validate_prerequisites(sop_id: str, precheck_stdout: str) -> Dict[str, Any]:
    """
    Validates cluster output against SOP prerequisite safety criteria.
    Args:
        sop_id: Unique identifier of the SOP being executed.
        precheck_stdout: Raw stdout from ansible_pcs_health_check or diagnostics tool.
    """
    norm_id = normalize_sop_id(sop_id)
    if norm_id not in SOP_CATALOG:
        return {"status": "ERROR", "error": f"Invalid SOP ID: {sop_id}"}
        
    violations = []
    text = precheck_stdout.lower()
    
    if "unquorate" in text or "not quorate" in text:
        violations.append("Cluster quorum lost: Cluster is not QUORATE.")
    if "stonith: disabled" in text:
        violations.append("STONITH fencing is disabled; rolling updates prohibited without fencing.")
    if "failcount" in text and "failcount: 0" not in text:
        violations.append("Active resource failcounts detected. Cleanup recommended before maintenance.")
        
    if violations:
        return {
            "status": "PREREQUISITE_FAILED",
            "sop_id": norm_id,
            "passed": False,
            "violations": violations,
            "recommended_action": "Execute ansible_fix_pcs to clear failcounts and restore quorum balance."
        }
        
    return {
        "status": "SUCCESS",
        "sop_id": norm_id,
        "passed": True,
        "message": "All SOP safety prerequisites verified successfully. Proceed with rolling execution."
    }

@mcp.tool()
def sop_generate_execution_plan(sop_id: str, entities: str, hitl_mode: str = "enforced") -> Dict[str, Any]:
    """
    Generates a structured execution plan graph for target entities based on SOP directives.
    Args:
        sop_id: SOP identifier to generate plan for.
        entities: Comma-separated list of target cluster names or server hostnames.
        hitl_mode: Current HITL guardrail mode ('enforced' or 'autonomous').
    """
    norm_id = normalize_sop_id(sop_id)
    if norm_id not in SOP_CATALOG:
        return {"status": "ERROR", "error": f"Invalid SOP ID: {sop_id}"}
        
    sop = SOP_CATALOG[norm_id]
    target_list = [e.strip() for e in entities.split(",") if e.strip()]
    
    return {
        "status": "SUCCESS",
        "sop_id": norm_id,
        "title": sop["title"],
        "target_count": len(target_list),
        "target_entities": target_list,
        "hitl_mode": hitl_mode,
        "requires_upfront_approval": bool(hitl_mode == "enforced" and sop["requires_hitl"]),
        "execution_stages": sop["stages"]
    }

if __name__ == "__main__":
    logger.info("Starting Dedicated SOP FastMCP Server on port 8001 (Streamable HTTP Transport)...")
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8001
    mcp.settings.transport_security.allowed_hosts.extend(["*", "sop-mcp:8001", "sop-mcp", "localhost", "127.0.0.1"])
    mcp.settings.transport_security.enable_dns_rebinding_protection = False
    mcp.run(transport="streamable-http")

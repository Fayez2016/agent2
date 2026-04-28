import os
import json
import requests
import urllib3
import time
import re
import builtins
from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AnsibleMCP")

mcp = FastMCP(
    "ansible",
    instructions="Dedicated Ansible Automation Platform (AAP) bridge for enterprise infrastructure management, specifically tuned for RHEL HA Cluster patching."
)

# --- HITL State Management ---
# In a real production system, this would be handled via a persistent DB or session-based tokens.
# For this simulation, we use a global state to track approvals.
_hitl_state = {
    "approved_action": None,
    "timestamp": 0
}

@mcp.tool()
def hitl_request_approval(action_summary: str) -> str:
    """
    CRITICAL: Human-in-the-Loop authorization gate.
    Presents the action summary to the administrator and waits for explicit Y/N approval.
    MUST be called before any high-risk maintenance tool.
    """
    print(f"\n==================================================")
    print(f"⚠️  ATTENTION REQUIRED - HITL APPROVAL ⚠️")
    print(f"==================================================")
    print(f"Hermes Agent is requesting permission to execute:")
    print(f"{action_summary}")
    print(f"==================================================")
    
    # logger.info used so it shows up in container logs
    logger.warning(f"HITL WAIT: Waiting for approval for action: {action_summary}")
    
    # FALLBACK FOR SIMULATION: 
    # In a containerized background process, builtins.input() will block indefinitely.
    # To allow the simulation to proceed while demonstrating the logic, 
    # we simulate the user typing 'Y' after a brief pause if a specific env var is set,
    # otherwise we use the requested builtins.input().
    
    if os.getenv("SIMULATE_HITL_AUTO_APPROVE") == "true":
        logger.info("SIMULATION MODE: Auto-approving HITL request...")
        choice = 'Y'
    else:
        try:
            choice = builtins.input("Do you approve this action? (Y/N): ").strip().upper()
        except EOFError:
            logger.error("HITL Error: No TTY attached to accept input. Auto-denying.")
            return "APPROVAL_DENIED - NO_TTY"

    if choice == 'Y':
        _hitl_state["approved_action"] = action_summary
        _hitl_state["timestamp"] = time.time()
        print("[✔] Approval Granted. Resuming agent execution...\n")
        return "APPROVAL_GRANTED"
    else:
        _hitl_state["approved_action"] = None
        print("[✖] Approval Denied. Halting agent execution...\n")
        return "APPROVAL_DENIED"

def check_approval(action_name: str):
    """Internal helper to verify if approval was granted for the current context."""
    # Check if approval exists and is less than 5 minutes old
    if _hitl_state["approved_action"] and (time.time() - _hitl_state["timestamp"] < 300):
        # In a real system, we'd check if action_name matches the summary. 
        # For simulation, we check if the agent mentioned the action.
        if action_name.lower() in _hitl_state["approved_action"].lower():
            return True
    return False

# --- Core Logic ---

def extract_debug_msg(stdout: str) -> Optional[str]:
    """Extract the 'msg' field from an Ansible debug task output block."""
    try:
        match = re.search(r'"msg":\s*"(.*?)"', stdout, re.DOTALL)
        if match:
            return match.group(1).replace('\\n', '\n').strip()
    except Exception:
        pass
    return None

def find_job_template(template_name: str, headers: dict, aap_host: str) -> int:
    protocol = "http" if "localhost" in aap_host or "aap-server" in aap_host else "https"
    url = f"{protocol}://{aap_host}/api/v2/job_templates"
    get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    resp = requests.get(url, headers=get_headers, params={"name": template_name}, verify=False)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Template '{template_name}' not found.")
    return results[0]["id"]

def launch_job(template_id: int, extra_vars: dict, headers: dict, aap_host: str) -> int:
    protocol = "http" if "localhost" in aap_host or "aap-server" in aap_host else "https"
    url = f"{protocol}://{aap_host}/api/v2/job_templates/{template_id}/launch/"
    payload = {"extra_vars": extra_vars}
    resp = requests.post(url, headers=headers, json=payload, verify=False)
    resp.raise_for_status()
    return resp.json()["job"]

def wait_for_completion(job_id: int, headers: dict, aap_host: str) -> str:
    protocol = "http" if "localhost" in aap_host or "aap-server" in aap_host else "https"
    while True:
        url = f"{protocol}://{aap_host}/api/v2/jobs/{job_id}/"
        get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
        resp = requests.get(url, headers=get_headers, verify=False)
        resp.raise_for_status()
        status = resp.json().get("status")
        if status in ["successful", "failed", "error", "canceled"]:
            return status
        time.sleep(2)

def get_job_output(job_id: int, headers: dict, aap_host: str) -> str:
    protocol = "http" if "localhost" in aap_host or "aap-server" in aap_host else "https"
    url = f"{protocol}://{aap_host}/api/v2/jobs/{job_id}/stdout/?format=txt"
    get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    resp = requests.get(url, headers=get_headers, verify=False)
    resp.raise_for_status()
    return resp.text

def run_ansible_job_logic(template_name: str, extra_vars: Dict[str, Any], is_high_risk: bool = False) -> str:
    # Check HITL Approval for high-risk tasks
    if is_high_risk:
        if not check_approval(template_name):
            return json.dumps({
                "status": "failed",
                "error": f"CRITICAL SECURITY VIOLATION: Execution of '{template_name}' blocked. No valid HITL approval found. You MUST call hitl_request_approval first."
            })

    aap_host = os.getenv("AAP_HOST")
    aap_token = os.getenv("AAP_TOKEN")

    if not aap_host or not aap_token:
        return json.dumps({"error": "AAP_HOST or AAP_TOKEN not configured"})

    headers = {
        "Authorization": f"Bearer {aap_token}",
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"Finding template: {template_name}")
        template_id = find_job_template(template_name, headers, aap_host)
        
        logger.info(f"Launching job with vars: {extra_vars}")
        job_id = launch_job(template_id, extra_vars, headers, aap_host)
        
        logger.info(f"Waiting for job {job_id} to complete...")
        status = wait_for_completion(job_id, headers, aap_host)
        
        logger.info(f"Job {job_id} finished with status: {status}. Fetching stdout...")
        stdout = get_job_output(job_id, headers, aap_host)
        
        clean_msg = extract_debug_msg(stdout)
        final_output = f"Result: {clean_msg}\n\nFull Output:\n{stdout}" if clean_msg else stdout

        return json.dumps({
            "status": status,
            "output": final_output,
            "job_id": job_id
        })
    except Exception as e:
        logger.error(f"Error in Ansible job: {str(e)}")
        return json.dumps({"error": str(e)})

# --- RHEL HA Recommended Practices Tools ---

@mcp.tool()
def ansible_pcs_node_standby(hostname: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Puts a specific cluster node in STANDBY mode to migrate resources off it."""
    return run_ansible_job_logic("PCS Node Standby", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_node_unstandby(hostname: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Takes a specific cluster node out of STANDBY mode."""
    return run_ansible_job_logic("PCS Node Unstandby", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_stop(hostname: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Stops the cluster software (Pacemaker/Corosync) on a specific node."""
    return run_ansible_job_logic("PCS Cluster Stop", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_start(hostname: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Starts the cluster software (Pacemaker/Corosync) on a specific node."""
    return run_ansible_job_logic("PCS Cluster Start", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_disable(hostname: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Disables the cluster services from starting at boot on a specific node."""
    return run_ansible_job_logic("PCS Cluster Disable", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_enable(hostname: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Enables the cluster services to start at boot on a specific node."""
    return run_ansible_job_logic("PCS Cluster Enable", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_health_check(hostname: str) -> str:
    """Retrieves a comprehensive health check for the PCS cluster from a node's perspective."""
    return run_ansible_job_logic("PCS Health Check", {"hostname": hostname})

@mcp.tool()
def ansible_pcs_cib_upgrade(hostname: str) -> str:
    """Upgrades the Cluster Information Base (CIB) to the latest supported version after a full cluster update."""
    return run_ansible_job_logic("PCS CIB Upgrade", {"hostname": hostname})

# --- Fleet Patching & Existing Tools ---

@mcp.tool()
def ansible_patch_fleet(hostlist: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Apply security patches to a fleet of servers (no reboot)."""
    return run_ansible_job_logic("Patch Fleet", {"hostlist": hostlist}, is_high_risk=True)

@mcp.tool()
def ansible_reboot_fleet(hostlist: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Reboot a fleet of servers."""
    return run_ansible_job_logic("Reboot Fleet", {"hostlist": hostlist}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_prepatch_check(hostlist: str) -> str:
    """Perform pre-patch validation across a fleet (Checks quorum and resource status)."""
    return run_ansible_job_logic("PCS Pre-Patch Check", {"hostlist": hostlist})

@mcp.tool()
def ansible_pcs_postpatch_check(hostlist: str) -> str:
    """Perform post-patch validation across a fleet (Checks resource recovery and health)."""
    return run_ansible_job_logic("PCS Post-Patch Check", {"hostlist": hostlist})

@mcp.tool()
def ansible_run_command(command: str, hostname: str) -> str:
    """Executes a shell command on a remote host via Ansible AAP."""
    return run_ansible_job_logic("Limited Run Any Command", {
        "hostlist": hostname,
        "agent_comand": command
    })

@mcp.tool()
def ansible_reboot_host(hostname: str) -> str:
    """Reboots a remote host via Ansible AAP."""
    return run_ansible_job_logic("Reboot Host", {"hostname": hostname})

@mcp.tool()
def ansible_install_package(hostname: str, package_name: str) -> str:
    """Installs a package on a remote host via Ansible AAP."""
    return run_ansible_job_logic("Install Package", {
        "hostname": hostname,
        "package_name": package_name
    })

@mcp.tool()
def ansible_expand_fs(hostname: str, mount_point: str, size_gb: int) -> str:
    """Expands a filesystem on a remote host via Ansible AAP."""
    return run_ansible_job_logic("Expand Filesystem", {
        "hostname": hostname,
        "mount_point": mount_point,
        "size_gb": size_gb
    })

@mcp.tool()
def ansible_fix_pcs(hostname: str) -> str:
    """Fixes PCS cluster issues on a remote host via Ansible AAP."""
    return run_ansible_job_logic("Fix PCS Cluster", {"hostname": hostname})

@mcp.tool()
def ansible_vmware_reset(hostname: str) -> str:
    """Performs a hard reset on a VM via VMware vCenter (triggered via AAP)."""
    return run_ansible_job_logic("VMware VM Reset", {"hostname": hostname})

@mcp.tool()
def ansible_pcs_status(hostname: str) -> str:
    """Retrieves the status of a PCS cluster on a specific host via AAP."""
    return run_ansible_job_logic("PCS Status", {"hostname": hostname})

@mcp.tool()
def ansible_send_email(hostname: str, email_to: str, message: str) -> str:
    """Sends a notification email regarding a specific host via AAP."""
    return run_ansible_job_logic("Send Email Notification", {
        "hostname": hostname,
        "email_to": email_to,
        "email_body": message
    })

if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8000
    mcp.settings.transport_security.allowed_hosts.extend(["*", "ansible-mcp:8000", "ansible-mcp"])
    mcp.settings.transport_security.enable_dns_rebinding_protection = False
    mcp.run(transport="streamable-http")

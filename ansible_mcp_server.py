import os
import json
import requests
import urllib3
import time
import re
import psycopg2
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
    instructions="Dedicated Ansible Automation Platform (AAP) bridge for enterprise infrastructure management. Uses a persistent PostgreSQL HITL approval gate."
)

# --- Database Helper ---

def get_db_connection():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("DATABASE_URL environment variable not set")
        raise RuntimeError("DATABASE_URL environment variable not set")
    return psycopg2.connect(db_url)

# --- HITL MCP Tool ---

@mcp.tool()
def hitl_request_approval(action_summary: str, action_name: str) -> str:
    """
    CRITICAL: Human-in-the-Loop authorization gate.
    Presents the action summary to the administrator via a web interface and waits for Y/N approval.
    
    REQUIRED:
    - action_summary: A detailed description of what you are doing and why.
    - action_name: MUST be the exact tool or template name you intend to execute (e.g. 'Patch Fleet', 'Reboot Host').
    
    You MUST call this before any tool marked as high-risk.
    """
    logger.warning(f"HITL REQUIRED: {action_summary} (Action: {action_name})")
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO hitl_requests (action_summary, action_name, status) VALUES (%s, %s, %s) RETURNING id",
            (action_summary, action_name, 'PENDING')
        )
        request_id = cur.fetchone()[0]
        conn.commit()
        
        logger.info(f"HITL Request {request_id} created. Waiting for resolution (60s timeout)...")
        
        # Poll for resolution with timeout
        timeout = 60
        start_time = time.time()
        while time.time() - start_time < timeout:
            cur.execute("SELECT status FROM hitl_requests WHERE id = %s", (request_id,))
            status = cur.fetchone()[0]
            if status != 'PENDING':
                break
            time.sleep(2)
        else:
            status = 'TIMEOUT'
        
        logger.info(f"HITL Request {request_id} resolved/expired: {status}")
        return json.dumps({
            "status": "successful" if status != 'TIMEOUT' else "failed",
            "approval": status,
            "request_id": request_id,
            "message": "Approval granted" if status == 'GRANTED' else "Approval denied" if status == 'DENIED' else "Timed out waiting for human approval. Please try again."
        })
    finally:
        cur.close()
        conn.close()

def check_approval(action_name: str) -> bool:
    """Helper to verify if a recently GRANTED HITL approval exists for this specific action."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Look for a GRANTED request in the last 10 minutes that matches the action name EXACTLY
        cur.execute(
            """SELECT id FROM hitl_requests 
               WHERE status = 'GRANTED' 
               AND action_name = %s 
               AND resolved_at > NOW() - INTERVAL '10 minutes'
               ORDER BY resolved_at DESC LIMIT 1""",
            (action_name,)
        )
        result = cur.fetchone()
        return result is not None
    finally:
        cur.close()
        conn.close()

# --- Core Ansible Logic ---

def extract_debug_msg(stdout: str) -> Optional[str]:
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
    # Enforcement: Block high-risk tasks without GRANTED status in DB
    if is_high_risk and not check_approval(template_name):
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
        template_id = find_job_template(template_name, headers, aap_host)
        job_id = launch_job(template_id, extra_vars, headers, aap_host)
        status = wait_for_completion(job_id, headers, aap_host)
        stdout = get_job_output(job_id, headers, aap_host)
        
        clean_msg = extract_debug_msg(stdout)
        final_output = f"Result: {clean_msg}\n\nFull Output:\n{stdout}" if clean_msg else stdout

        return json.dumps({
            "status": status,
            "output": final_output,
            "job_id": job_id
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool Definitions ---

@mcp.tool()
def ansible_get_server_info(hostlist: str) -> str:
    """Retrieve inventory information (HA status, planned reboot) for a list of servers."""
    return run_ansible_job_logic("Get Server Info", {"hostlist": hostlist})

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
def ansible_pcs_maintenance_mode(enable: bool) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Enable or disable global maintenance mode for the cluster."""
    mode = "true" if enable else "false"
    return run_ansible_job_logic("PCS Maintenance Mode", {"enable": mode}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_resource_move(resource_id: str, target_node: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Manually move a cluster resource to a specific node."""
    return run_ansible_job_logic("PCS Resource Move", {"resource_id": resource_id, "target_node": target_node}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_resource_clear(resource_id: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Clear temporary constraints for a cluster resource."""
    return run_ansible_job_logic("PCS Resource Clear", {"resource_id": resource_id}, is_high_risk=True)

@mcp.tool()
def ansible_reboot_host(hostname: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Reboot a single remote host."""
    return run_ansible_job_logic("Reboot Host", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_vmware_reset(vm_name: str) -> str:
    """CRITICAL: High-risk maintenance tool. Do not use for general admin tasks. You MUST obtain hitl_request_approval before using this.
    Hard reset a VM via VMware API."""
    return run_ansible_job_logic("VMware VM Reset", {"vm_name": vm_name}, is_high_risk=True)

# Standard tools (No HITL required)

@mcp.tool()
def ansible_install_package(hostname: str, package_name: str) -> str:
    """Installs a system package via DNF/YUM on a remote host."""
    return run_ansible_job_logic("Install Package", {"hostname": hostname, "package_name": package_name})

@mcp.tool()
def ansible_expand_fs(hostname: str, mount_point: str) -> str:
    """Expands a remote filesystem (LVM/XFS) on a specific host."""
    return run_ansible_job_logic("Expand Filesystem", {"hostname": hostname, "mount_point": mount_point})

@mcp.tool()
def ansible_fix_pcs(hostname: str) -> str:
    """Fix/Cleanup PCS cluster resources on a specific node."""
    return run_ansible_job_logic("Fix PCS Cluster", {"hostname": hostname})

@mcp.tool()
def ansible_pcs_status(hostname: str) -> str:
    """Retrieves the basic PCS Cluster health status from a node's perspective."""
    return run_ansible_job_logic("PCS Status", {"hostname": hostname})

@mcp.tool()
def ansible_send_email(recipient: str, subject: str, body: str) -> str:
    """Sends an automated email notification via Ansible AAP."""
    return run_ansible_job_logic("Send Email Notification", {"recipient": recipient, "subject": subject, "body": body})

@mcp.tool()
def ansible_pcs_health_check(hostname: str) -> str:
    """Retrieves a comprehensive health check for the PCS cluster from a node's perspective."""
    return run_ansible_job_logic("PCS Health Check", {"hostname": hostname})

@mcp.tool()
def ansible_pcs_cib_upgrade(hostname: str) -> str:
    """Upgrades the Cluster Information Base (CIB) to the latest supported version."""
    return run_ansible_job_logic("PCS CIB Upgrade", {"hostname": hostname})

@mcp.tool()
def ansible_pcs_constraint_list(hostname: str) -> str:
    """Retrieves the list of location constraints for the cluster."""
    return run_ansible_job_logic("PCS Constraint List", {"hostname": hostname})

@mcp.tool()
def ansible_run_command(command: str, hostname: str) -> str:
    """Executes a shell command on a remote host via Ansible AAP. 
    CRITICAL: High-risk maintenance tool. You MUST obtain hitl_request_approval before using this."""
    return run_ansible_job_logic("Limited Run Any Command", {"hostlist": hostname, "agent_comand": command}, is_high_risk=True)

if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8000
    # Relax security for local simulation
    mcp.settings.transport_security.allowed_hosts.extend(["*", "ansible-mcp:8000", "ansible-mcp", "localhost", "127.0.0.1"])
    mcp.settings.transport_security.enable_dns_rebinding_protection = False
    mcp.run(transport="streamable-http")

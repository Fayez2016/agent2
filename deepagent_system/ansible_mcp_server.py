import os
import json
import requests
import urllib3
import time
import re
import psycopg2
from typing import Dict, Any, Optional, Tuple
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

# --- HITL Helper Tool ---

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

    # If system is in autonomous mode, auto-approve immediately
    if get_hitl_mode() == "autonomous":
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO hitl_requests (action_summary, action_name, status, requested_at, resolved_at) VALUES (%s, %s, 'GRANTED', NOW(), NOW()) RETURNING id",
                (action_summary, action_name)
            )
            req_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"Autonomous Mode: Auto-approved HITL request #{req_id} for '{action_name}'.")
            return json.dumps({
                "status": "successful",
                "approval": "GRANTED",
                "request_id": req_id,
                "message": "Approval granted (Autonomous Mode)"
            })
        finally:
            cur.close()
            conn.close()

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
            cur.execute(
                "UPDATE hitl_requests SET status = 'TIMEOUT', resolved_at = NOW() WHERE id = %s AND status = 'PENDING'",
                (request_id,)
            )
            conn.commit()
        
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

def get_hitl_mode() -> str:
    """Queries system_settings table in PostgreSQL for current hitl_mode ('enforced' or 'autonomous')."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM system_settings WHERE key = 'hitl_mode' LIMIT 1;")
        row = cur.fetchone()
        if row:
            return str(row[0]).strip().lower()
    except Exception as e:
        logger.warning(f"Failed to query system_settings for hitl_mode: {e}")
    finally:
        cur.close()
        conn.close()
    return "enforced"

def check_approval(action_name: str) -> Optional[int]:
    """Verifies if an unconsumed GRANTED approval exists specifically for this action (supports aliases)."""
    conn = get_db_connection()
    cur = conn.cursor()
    names = [action_name]
    if action_name == "Limited Run Any Command":
        names.extend(["ansible_run_command", "Run Command", "Emergency Shell Command"])
    elif action_name == "ansible_run_command":
        names.append("Limited Run Any Command")
    elif action_name in ["Reboot Host", "Reboot Fleet"]:
        names.extend(["Reboot Host", "Reboot Fleet", "Fleet Reboot", "ansible_reboot_host", "ansible_reboot_fleet"])
    try:
        cur.execute(
            """SELECT id FROM hitl_requests 
               WHERE status = 'GRANTED'
               AND action_name = ANY(%s)
               AND resolved_at > NOW() - INTERVAL '5 minutes'
               ORDER BY resolved_at DESC LIMIT 1""",
            (names,)
        )
        result = cur.fetchone()
        return result[0] if result else None
    finally:
        cur.close()
        conn.close()

def consume_approval(req_id: int):
    """Marks a granted approval as consumed so subsequent operations must obtain fresh authorization."""
    if not req_id:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE hitl_requests SET status = 'CONSUMED' WHERE id = %s;", (req_id,))
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to consume HITL request #{req_id}: {e}")
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

TEMPLATE_ALIASES = {
    "Get Server Info": ["Get Server Info", "Check Host Online", "Server Info", "check_host_online", "get_server_info"],
    "Check Host Online": ["Check Host Online", "Get Server Info", "check_host_online"],
    "Reboot Host": ["Reboot Host", "Fleet Reboot", "Managed Reboot", "reboot_host", "fleet_reboot"],
    "Reboot Fleet": ["Reboot Fleet", "Fleet Reboot", "fleet_reboot", "reboot_fleet"],
    "Patch Fleet": ["Patch Fleet", "Fleet Patching", "fleet_patching", "patch_fleet"],
    "PCS Health Check": ["PCS Health Check", "HA Cluster Health Check", "ha_cluster_health_check", "pcs_cluster_health_check", "pcs_health_check"],
    "PCS Status": ["PCS Status", "HA Cluster Health Check", "pcs_status", "pcs_health_check"],
    "PCS Node Standby": ["PCS Node Standby", "HA Cluster Node Standby", "ha_cluster_node_standby", "pcs_node_standby"],
    "PCS Node Unstandby": ["PCS Node Unstandby", "HA Cluster Node Unstandby", "ha_cluster_node_unstandby", "pcs_node_unstandby"],
    "Fix PCS Cluster": ["Fix PCS Cluster", "PCS Fix Cluster", "pcs_fix_cluster"],
    "Console Power On": ["Console Power On", "Console Power On IPMI", "console_power_on_ipmi", "IPMI Power On", "IPMI Chassis Power", "ipmi_power_on", "ipmi"],
    "Limited Run Any Command": ["Limited Run Any Command", "Run Command", "Emergency Shell Command", "run_shell_command", "run_command"],
    "Expand Filesystem": ["Expand Filesystem", "Expand FS", "expand_filesystem"],
    "HA Rolling Update": ["HA Rolling Update", "ha_cluster_rolling_update", "rolling_update"],
    "Send Email Notification": ["Send Email Notification", "send_email_notification", "send_email"],
    "VMware VM Reset": ["VMware VM Reset", "vmware_vm_reset"]
}

def normalize_name(s: str) -> str:
    """Normalizes names by stripping non-alphanumerics and converting to lowercase."""
    return re.sub(r'[^a-z0-9]', '', str(s).lower())

def get_aap_api_base(aap_host: str, headers: dict) -> str:
    """Detects whether AAP uses the new /api/controller/v2/ (AAP 2.4/2.5/2.6) or legacy /api/v2/."""
    clean_host = aap_host.replace("https://", "").replace("http://", "").strip().rstrip("/")
    protocol = "http" if ("localhost" in clean_host or "127.0.0.1" in clean_host or "aap-server" in clean_host) else "https"
    
    controller_base = f"{protocol}://{clean_host}/api/controller/v2"
    legacy_base = f"{protocol}://{clean_host}/api/v2"
    
    get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    try:
        r = requests.get(f"{controller_base}/ping/", headers=get_headers, timeout=3, verify=False)
        if r.status_code in [200, 401, 403]:
            return controller_base
    except Exception:
        pass

    try:
        r = requests.get(f"{controller_base}/job_templates/", headers=get_headers, timeout=3, verify=False)
        if r.status_code in [200, 401, 403]:
            return controller_base
    except Exception:
        pass

    return legacy_base

def find_job_template(template_name: str, headers: dict, aap_host: str, api_base: Optional[str] = None) -> Tuple[int, str]:
    get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    if not api_base:
        api_base = get_aap_api_base(aap_host, headers)

    candidates = list(TEMPLATE_ALIASES.get(template_name, [template_name]))
    if template_name not in candidates:
        candidates.insert(0, template_name)

    norm_candidates = {normalize_name(c) for c in candidates}

    endpoints = [api_base]
    alt_base = api_base.replace("/api/controller/v2", "/api/v2") if "/controller" in api_base else api_base.replace("/api/v2", "/api/controller/v2")
    if alt_base not in endpoints:
        endpoints.append(alt_base)

    for base in endpoints:
        # 1. Fast path: Direct query with trailing slash
        for cand in candidates:
            try:
                url = f"{base}/job_templates/"
                resp = requests.get(url, headers=get_headers, params={"name": cand}, verify=False, timeout=5)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        logger.info(f"Resolved '{template_name}' to AAP Job Template '{results[0]['name']}' (ID {results[0]['id']}) via {base}")
                        return results[0]["id"], base
                elif resp.status_code >= 400:
                    logger.warning(f"AAP template query for '{cand}' returned {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.warning(f"Error querying template '{cand}' on {base}: {e}")

        # 2. Resilient path: Fetch template list and match via normalized fuzzy lookup
        try:
            url = f"{base}/job_templates/"
            resp = requests.get(url, headers=get_headers, params={"page_size": 200}, verify=False, timeout=8)
            if resp.status_code == 200:
                all_templates = resp.json().get("results", [])
                for item in all_templates:
                    item_name = item.get("name", "")
                    norm_item = normalize_name(item_name)
                    # Match exact normalized or substring (e.g. '03 - Fleet Reboot' matches 'fleetreboot')
                    if norm_item in norm_candidates or any(c in norm_item or norm_item in c for c in norm_candidates):
                        logger.info(f"Fuzzy-matched '{template_name}' to AAP Job Template '{item_name}' (ID {item['id']}) via {base}")
                        return item["id"], base

                discovered = [t.get("name") for t in all_templates[:25]]
                logger.info(f"AAP available templates on {base} ({len(all_templates)} total): {discovered}")
            elif resp.status_code >= 400:
                logger.warning(f"AAP template catalog query returned {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Error fetching template catalog on {base}: {e}")

    raise ValueError(f"Template '{template_name}' (aliases: {candidates}) not found on AAP ({api_base}).")

def launch_job(template_id: int, extra_vars: dict, headers: dict, api_base: str) -> int:
    url = f"{api_base}/job_templates/{template_id}/launch/"
    payload = {"extra_vars": extra_vars}
    resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=15)
    if resp.status_code >= 400:
        raise RuntimeError(f"AAP Job Launch Failed ({resp.status_code}) on {url}: {resp.text}")
    resp.raise_for_status()
    data = resp.json()
    job_id = data.get("id") or data.get("job")
    if not job_id:
        raise ValueError(f"No job ID returned in AAP launch response: {data}")
    return int(job_id)

def wait_for_completion(job_id: int, headers: dict, api_base: str) -> str:
    while True:
        url = f"{api_base}/jobs/{job_id}/"
        get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
        resp = requests.get(url, headers=get_headers, verify=False)
        resp.raise_for_status()
        status = resp.json().get("status")
        if status in ["successful", "failed", "error", "canceled"]:
            return status
        time.sleep(2)

def get_job_output(job_id: int, headers: dict, api_base: str) -> str:
    url = f"{api_base}/jobs/{job_id}/stdout/?format=txt"
    get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    resp = requests.get(url, headers=get_headers, verify=False)
    resp.raise_for_status()
    return resp.text

def run_ansible_job_logic(template_name: str, extra_vars: Dict[str, Any], is_high_risk: bool = False) -> str:
    # High-Risk Security & Autonomous Audit Trail Handling
    if is_high_risk:
        hitl_mode = get_hitl_mode()
        summary = f"Executing high-risk operation '{template_name}' with parameters {json.dumps(extra_vars)}"
        
        if hitl_mode == "autonomous":
            # Mode 1: 24/7 Autonomous (Auto-Approve with Audit Log)
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    """INSERT INTO hitl_requests (action_summary, action_name, status, requested_at, resolved_at) 
                       VALUES (%s, %s, 'AUTONOMOUS_GRANTED', NOW(), NOW()) RETURNING id;""",
                    (summary, template_name)
                )
                conn.commit()
                row = cur.fetchone()
                auto_req_id = row[0] if row else 0
                logger.info(f"Autonomous Mode: Auto-approved high-risk action '{template_name}' (Audit Request #{auto_req_id})")
            except Exception as e:
                logger.warning(f"Failed to record autonomous audit log: {e}")
            finally:
                cur.close()
                conn.close()
        else:
            # Mode 2: Guardrail Mode (Enforced HITL)
            req_id = check_approval(template_name)
            if not req_id:
                logger.warning(f"Enforced HITL: Execution of '{template_name}' blocked. No valid GRANTED approval in DB.")
                return json.dumps({
                    "status": "failed",
                    "error": f"CRITICAL SECURITY VIOLATION: Execution of '{template_name}' blocked. No valid HITL approval found. You MUST call hitl_request_approval(action_name='{template_name}', action_summary=...) first and wait for human operator authorization."
                })
            consume_approval(req_id)
            logger.info(f"Enforced HITL: Consumed approved request #{req_id} for '{template_name}'. Proceeding with execution.")

    # Dynamically resolve AAP Host & Token from PostgreSQL system_settings (with ENV fallback)
    aap_host = None
    aap_token = None
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT key, value FROM system_settings WHERE key IN ('aap_host', 'aap_token', 'ansible_backend_mode');")
        rows = dict(cur.fetchall())
        aap_host = rows.get("aap_host")
        aap_token = rows.get("aap_token")
    except Exception as e:
        logger.warning(f"Could not read AAP credentials from system_settings: {e}")
    finally:
        cur.close()
        conn.close()

    if not aap_host:
        aap_host = os.getenv("AAP_HOST")
    if not aap_token:
        aap_token = os.getenv("AAP_TOKEN")

    if not aap_host or not aap_token:
        return json.dumps({"error": "AAP_HOST or AAP_TOKEN not configured in PostgreSQL system_settings or Environment."})

    headers = {
        "Authorization": f"Bearer {aap_token}",
        "Content-Type": "application/json"
    }

    try:
        template_id, api_base = find_job_template(template_name, headers, aap_host)
        job_id = launch_job(template_id, extra_vars, headers, api_base)
        status = wait_for_completion(job_id, headers, api_base)
        stdout = get_job_output(job_id, headers, api_base)
        
        clean_msg = extract_debug_msg(stdout)
        final_output = f"Result: {clean_msg}\n\nFull Output:\n{stdout}" if clean_msg else stdout

        return json.dumps({
            "status": status,
            "output": final_output,
            "job_id": job_id
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Batch-Ready Tool Definitions (Accepts hostlist / comma-separated lists) ---

@mcp.tool()
def ansible_get_server_info(hostlist: str) -> str:
    """Retrieve inventory information (HA status, planned reboot) for a list of servers."""
    return run_ansible_job_logic("Get Server Info", {"hostlist": hostlist})

@mcp.tool()
def ansible_pcs_node_standby(hostlist: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Puts a specific cluster node or list of cluster nodes in STANDBY mode to migrate resources off."""
    return run_ansible_job_logic("PCS Node Standby", {"hostlist": hostlist}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_node_unstandby(hostlist: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Takes a specific cluster node or list of cluster nodes out of STANDBY mode."""
    return run_ansible_job_logic("PCS Node Unstandby", {"hostlist": hostlist}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_stop(hostname: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Stops the cluster software (Pacemaker/Corosync) on a specific node."""
    return run_ansible_job_logic("PCS Cluster Stop", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_start(hostname: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Starts the cluster software (Pacemaker/Corosync) on a specific node."""
    return run_ansible_job_logic("PCS Cluster Start", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_disable(hostname: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Disables the cluster services from starting at boot on a specific node."""
    return run_ansible_job_logic("PCS Cluster Disable", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_cluster_enable(hostname: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Enables the cluster services to start at boot on a specific node."""
    return run_ansible_job_logic("PCS Cluster Enable", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_patch_fleet(hostlist: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Apply security patches to a fleet or list of servers (no reboot)."""
    return run_ansible_job_logic("Patch Fleet", {"hostlist": hostlist}, is_high_risk=True)

@mcp.tool()
def ansible_reboot_fleet(hostlist: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Reboot a fleet or list of servers."""
    return run_ansible_job_logic("Reboot Fleet", {"hostlist": hostlist}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_maintenance_mode(enable: bool) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Enable or disable global maintenance mode for the cluster."""
    mode = "true" if enable else "false"
    return run_ansible_job_logic("PCS Maintenance Mode", {"enable": mode}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_resource_move(resource_id: str, target_node: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Manually move a cluster resource to a specific node."""
    return run_ansible_job_logic("PCS Resource Move", {"resource_id": resource_id, "target_node": target_node}, is_high_risk=True)

@mcp.tool()
def ansible_pcs_resource_clear(resource_id: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Clear temporary constraints for a cluster resource."""
    return run_ansible_job_logic("PCS Resource Clear", {"resource_id": resource_id}, is_high_risk=True)

@mcp.tool()
def ansible_reboot_host(hostname: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Reboot a single remote host."""
    return run_ansible_job_logic("Reboot Host", {"hostname": hostname}, is_high_risk=True)

@mcp.tool()
def ansible_vmware_reset(vm_name: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
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
def ansible_pcs_status(hostlist: str) -> str:
    """Retrieves the basic PCS Cluster health status from a list of nodes/clusters."""
    return run_ansible_job_logic("PCS Status", {"hostlist": hostlist})

@mcp.tool()
def ansible_send_email(recipient: str, subject: str, body: str) -> str:
    """Sends an automated email notification via Ansible AAP."""
    return run_ansible_job_logic("Send Email Notification", {"recipient": recipient, "subject": subject, "body": body})

@mcp.tool()
def ansible_pcs_health_check(hostlist: str) -> str:
    """Retrieves a comprehensive health check for PCS clusters from a list of hosts/clusters."""
    return run_ansible_job_logic("PCS Health Check", {"hostlist": hostlist})

@mcp.tool()
def ansible_pcs_cib_upgrade(hostname: str) -> str:
    """Upgrades the Cluster Information Base (CIB) to the latest supported version."""
    return run_ansible_job_logic("PCS CIB Upgrade", {"hostname": hostname})

@mcp.tool()
def ansible_pcs_constraint_list(hostname: str) -> str:
    """Retrieves the list of location constraints for the cluster."""
    return run_ansible_job_logic("PCS Constraint List", {"hostname": hostname})

@mcp.tool()
def ansible_check_host_online(hostlist: str) -> str:
    """Verifies that remote hosts are online and reachable on SSH port 22 after reboot."""
    return run_ansible_job_logic("Check Host Online", {"hostlist": hostlist})

@mcp.tool()
def ansible_console_power_on(hostlist: str) -> str:
    """High-risk maintenance tool requiring human approval gate.
    Brings up an unresponsive server via out-of-band management console / IPMI."""
    return run_ansible_job_logic("Console Power On", {"hostlist": hostlist}, is_high_risk=True)

@mcp.tool()
def ansible_run_command(command: str, hostname: str) -> str:
    """Executes a shell command on a remote host via Ansible AAP. 
    High-risk maintenance tool requiring human approval gate."""
    return run_ansible_job_logic("Limited Run Any Command", {"hostlist": hostname, "command": command, "agent_comand": command}, is_high_risk=True)

if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8000
    # Relax security for local simulation
    mcp.settings.transport_security.allowed_hosts.extend(["*", "ansible-mcp:8000", "ansible-mcp", "localhost", "127.0.0.1"])
    mcp.settings.transport_security.enable_dns_rebinding_protection = False
    mcp.run(transport="streamable-http")

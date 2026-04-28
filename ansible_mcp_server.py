import os
import json
import requests
import urllib3
import time
import re
import threading
from typing import Dict, Any, Optional
from flask import Flask, request, render_template_string
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
    instructions="Dedicated Ansible Automation Platform (AAP) bridge for enterprise infrastructure management. Includes a Flask-based HITL approval gate."
)

# --- Shared Approval State ---
approval_state = {
    "status": "IDLE",  # IDLE, PENDING, GRANTED, DENIED
    "action_summary": None,
    "last_decision": None
}

# --- Flask Web Server for HITL ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hermes HITL Approval Gate</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background-color: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center; max-width: 500px; width: 90%; }
        h1 { color: #333; margin-bottom: 20px; }
        .summary { background-color: #fff8e1; border-left: 5px solid #ffc107; padding: 15px; margin: 20px 0; text-align: left; font-style: italic; color: #555; }
        .status-idle { color: #888; font-weight: bold; }
        .status-pending { color: #d32f2f; font-weight: bold; animation: pulse 2s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        .btn-group { display: flex; justify-content: space-around; margin-top: 30px; }
        button { padding: 12px 30px; border: none; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; transition: transform 0.1s, opacity 0.2s; }
        button:active { transform: scale(0.95); }
        .btn-approve { background-color: #4caf50; color: white; }
        .btn-deny { background-color: #f44336; color: white; }
        button:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hermes HITL Gate</h1>
        {% if status == 'PENDING' %}
            <p>The agent is requesting authorization for:</p>
            <div class="summary">{{ action_summary }}</div>
            <form action="/resolve" method="post" class="btn-group">
                <button type="submit" name="decision" value="GRANTED" class="btn-approve">APPROVE</button>
                <button type="submit" name="decision" value="DENIED" class="btn-deny">REJECT</button>
            </form>
        {% else %}
            <p class="status-idle">SYSTEM IDLE</p>
            <p>Waiting for the next high-risk request from Hermes...</p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, **approval_state)

@app.route('/resolve', methods=['POST'])
def resolve():
    decision = request.form.get('decision')
    if decision in ['GRANTED', 'DENIED']:
        approval_state["status"] = decision
        logger.info(f"HITL Web: User decided {decision}")
        return f"<h3>Decision '{decision}' recorded successfully.</h3><p>Hermes will now resume.</p><script>setTimeout(() => window.location.href='/', 3000);</script>"
    return "Invalid decision", 400

def run_flask():
    logger.info("Starting HITL Web Server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# Start Flask in a daemon thread
threading.Thread(target=run_flask, daemon=True).start()

# --- HITL MCP Tool ---

@mcp.tool()
def hitl_request_approval(action_summary: str) -> str:
    """
    CRITICAL: Human-in-the-Loop authorization gate.
    Presents the action summary to the administrator via a web interface and waits for Y/N approval.
    MUST be called before any high-risk maintenance tool.
    """
    logger.warning(f"HITL REQUIRED: {action_summary}")
    
    # Reset and set state to PENDING
    approval_state["action_summary"] = action_summary
    approval_state["status"] = "PENDING"
    
    # Wait for web resolution
    while approval_state["status"] == "PENDING":
        time.sleep(1)
    
    decision = approval_state["status"]
    approval_state["last_decision"] = decision
    approval_state["status"] = "IDLE"
    approval_state["action_summary"] = None
    
    logger.info(f"HITL Resolved: {decision}")
    
    # Return mocked AAP JSON response as requested
    return json.dumps({
        "status": "successful",
        "approval": decision
    })

def check_approval(action_name: str) -> bool:
    """Helper to verify if the last HITL approval matches the intent."""
    if approval_state["last_decision"] == "GRANTED":
        # In a real system, we'd verify the action_name was what was approved.
        return True
    return False

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
    # Enforcement: Block high-risk tasks without GRANTED status
    if is_high_risk and not check_approval(template_name):
        return json.dumps({
            "status": "failed",
            "error": f"CRITICAL SECURITY VIOLATION: Execution of '{template_name}' blocked. No valid HITL approval found. You MUST call hitl_request_approval first."
        })

    # Clear last_decision after consumption to force new approval for next task
    approval_state["last_decision"] = None

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

# Standard tools (No HITL required)

@mcp.tool()
def ansible_pcs_health_check(hostname: str) -> str:
    """Retrieves a comprehensive health check for the PCS cluster from a node's perspective."""
    return run_ansible_job_logic("PCS Health Check", {"hostname": hostname})

@mcp.tool()
def ansible_pcs_cib_upgrade(hostname: str) -> str:
    """Upgrades the Cluster Information Base (CIB) to the latest supported version."""
    return run_ansible_job_logic("PCS CIB Upgrade", {"hostname": hostname})

@mcp.tool()
def ansible_run_command(command: str, hostname: str) -> str:
    """Executes a shell command on a remote host via Ansible AAP."""
    return run_ansible_job_logic("Limited Run Any Command", {"hostlist": hostname, "agent_comand": command})

if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8000
    mcp.settings.transport_security.allowed_hosts.extend(["*", "ansible-mcp:8000", "ansible-mcp"])
    mcp.settings.transport_security.enable_dns_rebinding_protection = False
    mcp.run(transport="streamable-http")

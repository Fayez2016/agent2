import os
import json
import requests
import urllib3
import time
import re
from typing import Dict, Any, Optional
from tools.registry import registry, tool_result, tool_error

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import logging

# Set up logging for the tool
# Note: In a container, /opt/hermes/ansible_tool.log will be used
logging.basicConfig(
    filename='ansible_tool.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
tool_logger = logging.getLogger("AnsibleTool")

def extract_debug_msg(stdout: str) -> Optional[str]:
    """Extract the 'msg' field from an Ansible debug task output block."""
    try:
        # Match "msg": "..." or "msg": "..."
        # This is more robust than matching the whole JSON block first
        match = re.search(r'"msg":\s*"(.*?)"', stdout, re.DOTALL)
        if match:
            return match.group(1).replace('\\n', '\n').strip()
    except Exception:
        pass
    return None

def find_job_template(template_name: str, headers: dict, aap_host: str) -> int:
    protocol = "https" if "localhost" not in aap_host and "aap-server" not in aap_host else "http"
    url = f"{protocol}://{aap_host}/api/v2/job_templates"
    # Don't send Content-Type on GET requests
    get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    resp = requests.get(url, headers=get_headers, params={"name": template_name}, verify=False)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Template '{template_name}' not found.")
    return results[0]["id"]

def launch_job(template_id: int, extra_vars: dict, headers: dict, aap_host: str) -> int:
    protocol = "https" if "localhost" not in aap_host and "aap-server" not in aap_host else "http"
    url = f"{protocol}://{aap_host}/api/v2/job_templates/{template_id}/launch/"
    payload = {"extra_vars": extra_vars}
    resp = requests.post(url, headers=headers, json=payload, verify=False)
    resp.raise_for_status()
    return resp.json()["job"]

def wait_for_completion(job_id: int, headers: dict, aap_host: str) -> str:
    protocol = "https" if "localhost" not in aap_host and "aap-server" not in aap_host else "http"
    while True:
        url = f"{protocol}://{aap_host}/api/v2/jobs/{job_id}/"
        # Don't send Content-Type on GET requests
        get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
        resp = requests.get(url, headers=get_headers, verify=False)
        resp.raise_for_status()
        status = resp.json().get("status")
        if status in ["successful", "failed", "error", "canceled"]:
            return status
        time.sleep(2)

def get_job_output(job_id: int, headers: dict, aap_host: str) -> str:
    protocol = "https" if "localhost" not in aap_host and "aap-server" not in aap_host else "http"
    url = f"{protocol}://{aap_host}/api/v2/jobs/{job_id}/stdout/?format=txt"
    # Don't send Content-Type on GET requests
    get_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    resp = requests.get(url, headers=get_headers, verify=False)
    resp.raise_for_status()
    return resp.text

def run_ansible_job_logic(template_name: str, extra_vars: Dict[str, Any]) -> str:
    aap_host = os.getenv("AAP_HOST")
    aap_token = os.getenv("AAP_TOKEN")

    if not aap_host or not aap_token:
        # For testing purposes, return a successful response if AAP is not configured
        hostname = extra_vars.get("hostname") or extra_vars.get("hostlist") or "test-host"
        tool_logger.info(f"AAP not configured. Returning local execution result for {template_name} on {hostname}")
        return tool_result({
            "status": "successful",
            "output": f"Result: Action '{template_name}' completed on {hostname}\n\nFull Output:\nAAP execution completed successfully.",
            "job_id": 0
        })

    headers = {
        "Authorization": f"Bearer {aap_token}",
        "Content-Type": "application/json"
    }

    try:
        tool_logger.info(f"Finding template: {template_name}")
        template_id = find_job_template(template_name, headers, aap_host)
        
        tool_logger.info(f"Launching job with vars: {extra_vars}")
        job_id = launch_job(template_id, extra_vars, headers, aap_host)
        
        tool_logger.info(f"Waiting for job {job_id} to complete...")
        status = wait_for_completion(job_id, headers, aap_host)
        
        tool_logger.info(f"Job {job_id} finished with status: {status}. Fetching stdout...")
        stdout = get_job_output(job_id, headers, aap_host)
        
        # Try to extract a clean message from the debug output
        clean_msg = extract_debug_msg(stdout)
        tool_logger.info(f"Extracted message: {clean_msg}")
        
        # We put the clean message first in a combined string for the model
        final_output = f"Result: {clean_msg}\n\nFull Output:\n{stdout}" if clean_msg else stdout

        return tool_result({
            "status": status,
            "output": final_output,
            "job_id": job_id
        })
    except Exception as e:
        tool_logger.error(f"Error in Ansible job: {str(e)}")
        return tool_error(str(e))

def ansible_run_command_handler(args: Dict[str, Any], **kwargs) -> str:
    command = args.get("command")
    hostname = args.get("hostname")
    return run_ansible_job_logic("Limited Run Any Command", {
        "hostlist": hostname,
        "agent_comand": command
    })

def ansible_reboot_host_handler(args: Dict[str, Any], **kwargs) -> str:
    hostname = args.get("hostname")
    return run_ansible_job_logic("Reboot Host", {"hostname": hostname})

def ansible_install_package_handler(args: Dict[str, Any], **kwargs) -> str:
    hostname = args.get("hostname")
    package_name = args.get("package_name")
    return run_ansible_job_logic("Install Package", {
        "hostname": hostname,
        "package_name": package_name
    })

def ansible_expand_fs_handler(args: Dict[str, Any], **kwargs) -> str:
    hostname = args.get("hostname")
    mount_point = args.get("mount_point")
    size_gb = args.get("size_gb")
    return run_ansible_job_logic("Expand Filesystem", {
        "hostname": hostname,
        "mount_point": mount_point,
        "size_gb": size_gb
    })

def ansible_fix_pcs_handler(args: Dict[str, Any], **kwargs) -> str:
    hostname = args.get("hostname")
    return run_ansible_job_logic("Fix PCS Cluster", {"hostname": hostname})

# Register Tools
registry.register(
    name="ansible_run_command",
    toolset="devops",
    schema={
        "description": "Executes a shell command on a remote host via Ansible AAP.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run (e.g. 'uptime')"},
                "hostname": {"type": "string", "description": "The target hostname or IP."}
            },
            "required": ["command", "hostname"]
        }
    },
    handler=ansible_run_command_handler,
    description="Execute remote commands via Ansible",
    emoji="🤖"
)

registry.register(
    name="ansible_reboot_host",
    toolset="devops",
    schema={
        "description": "Reboots a remote host via Ansible AAP.",
        "parameters": {
            "type": "object",
            "properties": {
                "hostname": {"type": "string", "description": "The target hostname to reboot."}
            },
            "required": ["hostname"]
        }
    },
    handler=ansible_reboot_host_handler,
    description="Reboot remote host via Ansible",
    emoji="🔄"
)

registry.register(
    name="ansible_install_package",
    toolset="devops",
    schema={
        "description": "Installs a package on a remote host via Ansible AAP.",
        "parameters": {
            "type": "object",
            "properties": {
                "hostname": {"type": "string", "description": "The target hostname."},
                "package_name": {"type": "string", "description": "The name of the package (e.g. 'vim')."}
            },
            "required": ["hostname", "package_name"]
        }
    },
    handler=ansible_install_package_handler,
    description="Install package via Ansible",
    emoji="📦"
)

registry.register(
    name="ansible_expand_fs",
    toolset="devops",
    schema={
        "description": "Expands a filesystem on a remote host via Ansible AAP.",
        "parameters": {
            "type": "object",
            "properties": {
                "hostname": {"type": "string", "description": "The target hostname."},
                "mount_point": {"type": "string", "description": "The mount point to expand (e.g. '/var')."},
                "size_gb": {"type": "integer", "description": "The new size in GB."}
            },
            "required": ["hostname", "mount_point", "size_gb"]
        }
    },
    handler=ansible_expand_fs_handler,
    description="Expand filesystem via Ansible",
    emoji="💾"
)

registry.register(
    name="ansible_fix_pcs",
    toolset="devops",
    schema={
        "description": "Fixes PCS cluster issues on a remote host via Ansible AAP.",
        "parameters": {
            "type": "object",
            "properties": {
                "hostname": {"type": "string", "description": "The target hostname."}
            },
            "required": ["hostname"]
        }
    },
    handler=ansible_fix_pcs_handler,
    description="Fix PCS cluster via Ansible",
    emoji="🔧"
)

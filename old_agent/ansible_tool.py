import requests
import json
import time
import os
import urllib3
from typing import Optional, Dict, Any

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def find_job_template(template_name: str, headers: dict, aap_host: str) -> int:
    url = f"https://{aap_host}/api/v2/job_templates"
    resp = requests.get(url, headers=headers, params={"name": template_name}, verify=False)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Template '{template_name}' not found.")
    return results[0]["id"]

def launch_job(template_id: int, extra_vars: dict, headers: dict, aap_host: str) -> int:
    url = f"https://{aap_host}/api/v2/job_templates/{template_id}/launch/"
    payload = {
        "extra_vars": extra_vars
    }
    print("📤 Launching job with payload:")
    print(json.dumps(payload, indent=2))

    resp = requests.post(url, headers=headers, json=payload, verify=False)

    if resp.status_code != 201:
        print("🚫 Launch failed. Response:")
        print(f"Status Code: {resp.status_code}")
        print("Response Body:")
        print(resp.text)
        resp.raise_for_status()

    return resp.json()["job"]

def wait_for_completion(job_id: int, headers: dict, aap_host: str) -> str:
    while True:
        url = f"https://{aap_host}/api/v2/jobs/{job_id}/"
        resp = requests.get(url, headers=headers, verify=False)
        resp.raise_for_status()
        status = resp.json().get("status")
        print(f"Status: {status}")
        if status in ["successful", "failed", "error", "canceled"]:
            return status
        time.sleep(5)

def get_job_output(job_id: int, headers: dict, aap_host: str) -> str:
    url = f"https://{aap_host}/api/v2/jobs/{job_id}/stdout/?format=txt"
    resp = requests.get(url, headers=headers, verify=False)
    resp.raise_for_status()
    return resp.text

def extract_debug_task_output(full_output: str) -> str:
    """
    Extracts from the line:
    'TASK [Report output to the agent using debug var]'
    all the way to the end of the output, including PLAY RECAP.
    """
    start_marker = "TASK [Report output to the agent using debug var]"

    lines = full_output.splitlines()
    result =[]
    capture = False

    for line in lines:
        # Start capturing when we hit the debug task line
        if line.startswith(start_marker):
            capture = True

        # If capturing, add the line
        if capture:
            result.append(line)

    # Return everything from the debug task to the end
    return "\n".join(result)

def run_ansible_job(template_name: str, extra_vars: Dict[str, Any], aap_host: Optional[str] = None, aap_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Run an Ansible job as a tool for LangGraph.

    Args:
        template_name (str): Name of the job template in AAP.
        extra_vars (dict): Variables to pass to the job template.
        aap_host (str, optional): AAP host URL. Defaults to environment variable.
        aap_token (str, optional): AAP token. Defaults to environment variable.

    Returns:
        dict: A structured result dict suitable for LangGraph tools.
    """
    AAP_HOST = aap_host or os.getenv("AAP_HOST")
    AAP_TOKEN = aap_token or os.getenv("AAP_TOKEN")

    if not AAP_HOST or not AAP_TOKEN:
        raise EnvironmentError("Missing AAP_HOST or AAP_TOKEN environment variables.")

    headers = {
        "Authorization": f"Bearer {AAP_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        # Step 1: Find template
        template_id = find_job_template(template_name, headers, AAP_HOST)

        # Step 2: Launch job
        job_id = launch_job(template_id, extra_vars, headers, AAP_HOST)

        # Step 3: Wait for completion
        status = wait_for_completion(job_id, headers, AAP_HOST)

        # Step 4: Get output
        output2 = get_job_output(job_id, headers, AAP_HOST)

        # Step 5: Format the output
        output = extract_debug_task_output(output2)

        return {
            "job_id": job_id,
            "status": status,
            "output": output,
            "template": template_name,
            "extra_vars": extra_vars
        }
    except Exception as e:
        return {
            "error": str(e),
            "template": template_name,
            "extra_vars": extra_vars
        }

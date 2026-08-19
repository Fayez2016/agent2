from flask import Flask, request, jsonify
import random
import time
import logging
import sys
import json
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('aap_server.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AAP-Server")

app = Flask(__name__)

# Define 10 HA Clusters with 2 nodes each
HA_CLUSTERS = {
    f"ha-cluster-{i:02d}": [f"rhel-ha-{i:02d}-node1", f"rhel-ha-{i:02d}-node2"]
    for i in range(1, 11)
}

# Standalone Fleet
FLEET_SERVERS = [f"rhel-prod-{i:02d}" for i in range(1, 11)]

# State tracking for simulated console recovery
CONSOLE_RECOVERED_HOSTS = set()

# Template ID mapping
TEMPLATE_MAP = {
    "Limited Run Any Command": 101,
    "Reboot Host": 102,
    "Install Package": 103,
    "Expand Filesystem": 104,
    "Fix PCS Cluster": 105,
    "Patch Fleet": 110,
    "Reboot Fleet": 111,
    "PCS Pre-Patch Check": 112,
    "PCS Post-Patch Check": 113,
    "VMware VM Reset": 107,
    "PCS Status": 108,
    "Send Email Notification": 109,
    "PCS Node Standby": 114,
    "PCS Node Unstandby": 115,
    "PCS Cluster Stop": 116,
    "PCS Cluster Start": 117,
    "PCS Cluster Disable": 118,
    "PCS Cluster Enable": 119,
    "PCS Health Check": 120,
    "PCS CIB Upgrade": 121,
    "PCS Maintenance Mode": 122,
    "PCS Resource Move": 123,
    "PCS Resource Clear": 124,
    "PCS Constraint List": 125,
    "Get Server Info": 126,
    "Check Host Online": 127,
    "Console Power On": 128,
    "HA Rolling Update": 129
}

# Job storage
jobs = {}

def get_iso_now():
    return datetime.utcnow().isoformat() + "Z"

@app.route('/api/v2/job_templates', methods=['GET'])
def get_job_templates():
    name = request.args.get('name')
    template_id = TEMPLATE_MAP.get(name, 200)
    
    return jsonify({
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": template_id,
                "type": "job_template",
                "url": f"/api/v2/job_templates/{template_id}/",
                "name": name,
                "description": f"Verbatim mock for {name}",
                "job_type": "run",
                "inventory": 1,
                "project": 1,
                "playbook": f"{name.lower().replace(' ', '_')}.yml",
                "created": "2026-01-01T12:00:00.000000Z",
                "modified": get_iso_now()
            }
        ]
    })

@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'])
def launch_job(template_id):
    job_id = random.randint(10000, 99999)
    extra_vars = {}
    if request.is_json:
        data = request.get_json(silent=True)
        if data:
            extra_vars = data.get('extra_vars', {})
    
    # State tracking for console recovery
    if template_id in [107, 128]: # VMware Reset or Console Power On
        h = extra_vars.get('hostname') or extra_vars.get('vm_name') or extra_vars.get('target_host', '')
        if h:
            CONSOLE_RECOVERED_HOSTS.add(h)

    status = "successful"
    jobs[job_id] = {
        "id": job_id,
        "status": status,
        "extra_vars": extra_vars,
        "template_id": template_id,
        "start_time": time.time(),
        "created": get_iso_now()
    }
    
    return jsonify({
        "job": job_id,
        "type": "job",
        "url": f"/api/v2/jobs/{job_id}/"
    }), 201

@app.route('/api/v2/jobs/<int:job_id>/', methods=['GET'])
def get_job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"detail": "Not found."}), 404
    
    elapsed = time.time() - job["start_time"]
    current_status = "running" if elapsed < 0.2 else job["status"]
    
    return jsonify({
        "id": job_id,
        "type": "job",
        "url": f"/api/v2/jobs/{job_id}/",
        "name": "Simulated Job",
        "status": current_status,
        "failed": current_status == "failed",
        "started": job["created"],
        "finished": get_iso_now() if current_status != "running" else None,
        "job_template": job["template_id"],
        "extra_vars": json.dumps(job["extra_vars"])
    })

def generate_multi_host_patch_stdout(template_id, extra_vars, status):
    hostlist_raw = extra_vars.get('hostlist') or extra_vars.get('hostname', '')
    if isinstance(hostlist_raw, list):
        targets = hostlist_raw
    elif isinstance(hostlist_raw, str):
        targets = [h.strip() for h in hostlist_raw.split(',') if h.strip()]
    else:
        targets = FLEET_SERVERS

    output = []
    t_name = "Patch Fleet" if template_id == 110 else "Reboot Fleet"
    output.append(f"PLAY [{t_name}] ************************************************************")
    output.append("TASK [Gathering Facts] *********************************************************")
    for t in targets:
        output.append(f"ok: [{t}]")
    output.append("")
    output.append(f"TASK [{t_name} Execution] ****************************************************")
    for t in targets:
        output.append(f"changed: [{t}]")
    output.append("")
    summary = {
        "total": len(targets),
        "successful": len(targets),
        "failed": 0,
        "reboot_required_count": len(targets)
    }
    output.append("ok: [localhost] => {")
    output.append(f"    \"msg\": \"{t_name} process completed across {len(targets)} servers.\",")
    output.append(f"    \"summary\": {json.dumps(summary, indent=8)}")
    output.append("}")
    output.append("")
    output.append("PLAY RECAP *********************************************************************")
    for t in targets:
        output.append(f"{t:30} : ok=3    changed=1    unreachable=0    failed=0")
    return "\n".join(output)

@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'])
def get_job_stdout(job_id):
    job = jobs.get(job_id)
    if not job:
        return "Not found", 404
    
    template_id = job["template_id"]
    extra_vars = job["extra_vars"]
    hostname = str(extra_vars.get('hostname') or extra_vars.get('hostlist') or extra_vars.get('vm_name') or 'target-host')

    # Multi-host fleet operations
    if template_id in [110, 111]:
        return generate_multi_host_patch_stdout(template_id, extra_vars, job["status"])

    # Template 127: Check Host Online
    if template_id == 127:
        # Check if this host is simulated as soft hang
        if "node2" in hostname and hostname not in CONSOLE_RECOVERED_HOSTS:
            # First check before console recovery: Offline/Unresponsive
            msg = f"Host {hostname} is OFFLINE / UNRESPONSIVE (Port 22 unreachable after reboot timeout)."
            state = "failed"
        else:
            # Host online
            msg = f"Host {hostname} is ONLINE (Port 22 Reachable). Uptime: 45 seconds."
            state = "successful"
        return f"""
PLAY [Check Host Online] *******************************************************
TASK [Test Port 22] ************************************************************
ok: [{hostname}] => {{
    "msg": "{msg}",
    "online": {"true" if state == "successful" else "false"},
    "status": "{state}"
}}
PLAY RECAP *********************************************************************
{hostname:30} : ok=2    changed=0    unreachable=0    failed={0 if state == 'successful' else 1}
"""

    # Template 128: Console Power On / Out-of-band IPMI
    if template_id == 128:
        CONSOLE_RECOVERED_HOSTS.add(hostname)
        msg = f"Out-of-band console power-on issued for {hostname}. Status: SUCCESSFUL. Node booted."
        return f"""
PLAY [Console Power On] ********************************************************
TASK [Power On via IPMI/Console] ***********************************************
ok: [{hostname}] => {{
    "msg": "{msg}",
    "power_state": "on",
    "status": "successful"
}}
PLAY RECAP *********************************************************************
{hostname:30} : ok=2    changed=1    unreachable=0    failed=0
"""

    # Template 107: VMware VM Reset
    if template_id == 107:
        CONSOLE_RECOVERED_HOSTS.add(hostname)
        msg = f"VMware reset successfully executed for VM {hostname}. Node rebooted from hypervisor."
        return f"""
PLAY [VMware VM Reset] *********************************************************
TASK [Hard Reset VM] ***********************************************************
ok: [{hostname}] => {{
    "msg": "{msg}",
    "status": "successful"
}}
PLAY RECAP *********************************************************************
{hostname:30} : ok=2    changed=1    unreachable=0    failed=0
"""

    # Template 109: Send Email Notification
    if template_id == 109:
        recipient = extra_vars.get('recipient', 'admin@enterprise.local')
        subj = extra_vars.get('subject', '[SRE Report] Maintenance Completed')
        msg = f"Notification email successfully dispatched to {recipient}. Subject: '{subj}'."
        return f"""
PLAY [Send Email Notification] *************************************************
TASK [Dispatch Email] **********************************************************
ok: [localhost] => {{
    "msg": "{msg}",
    "recipient": "{recipient}",
    "status": "successful"
}}
PLAY RECAP *********************************************************************
localhost                      : ok=2    changed=1    unreachable=0    failed=0
"""

    # Cluster SOP Templates
    msg = f"Operation completed on {hostname}"
    if template_id == 114:
        msg = f"Node {hostname} put in STANDBY mode. Cluster resources evacuated to active peer nodes."
    elif template_id == 115:
        msg = f"Node {hostname} taken out of STANDBY mode. Cluster resources balanced and healthy."
    elif template_id == 120:
        msg = f"Health Check: PASS - Cluster for {hostname} is active, stonith enabled, and quorate."
    elif template_id == 108:
        msg = f"PCS Status: Cluster quorate, 2 nodes configured, 0 failed resources on {hostname}."
    elif template_id == 102:
        msg = f"Reboot completed on {hostname}. Elapsed: 38 seconds."
    elif template_id == 105:
        msg = f"PCS resource cleanup completed on {hostname}."

    return f"""
PLAY [Job] *********************************************************************
TASK [Execute Action] **********************************************************
ok: [{hostname}] => {{
    "msg": "{msg}",
    "changed": true,
    "status": "{job['status']}"
}}
PLAY RECAP *********************************************************************
{hostname:30} : ok=2    changed=1    unreachable=0    failed=0
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

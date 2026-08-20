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

FLEET_SERVERS = [f"rhel-prod-{i:02d}.enterprise.local" for i in range(1, 21)]

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
    "Get Server Info": 126
}

# Job storage
jobs = {}

# Inventory mock data
INVENTORY_DATA = {
    "rhel-prod-01.enterprise.local": {"is_ha": True, "planned_reboot": False},
    "rhel-prod-02.enterprise.local": {"is_ha": True, "planned_reboot": False},
    "rhel-app-01.enterprise.local": {"is_ha": False, "planned_reboot": True},
    "rhel-app-02.enterprise.local": {"is_ha": False, "planned_reboot": False},
}

def get_iso_now():
    return datetime.utcnow().isoformat() + "Z"

@app.route('/api/v2/job_templates', methods=['GET'])
def get_job_templates():
    name = request.args.get('name')
    template_id = TEMPLATE_MAP.get(name, 200)
    
    # Verbatim AAP response structure
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
        if data: extra_vars = data.get('extra_vars', {})
    
    status = "successful"
    # Failure simulation
    if template_id in [110, 112, 113, 120, 121] and random.random() < 0.10:
        status = "failed"
    
    jobs[job_id] = {
        "id": job_id,
        "status": status,
        "extra_vars": extra_vars,
        "template_id": template_id,
        "start_time": time.time(),
        "created": get_iso_now()
    }
    
    # Verbatim launch response
    return jsonify({
        "job": job_id,
        "type": "job",
        "url": f"/api/v2/jobs/{job_id}/"
    }), 201

@app.route('/api/v2/jobs/<int:job_id>/', methods=['GET'])
def get_job_status(job_id):
    job = jobs.get(job_id)
    if not job: return jsonify({"detail": "Not found."}), 404
    
    elapsed = time.time() - job["start_time"]
    current_status = "running" if elapsed < 0.5 else job["status"]
    
    # Verbatim job status response
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

def generate_fleet_stdout(template_id, status):
    output = []
    t_name = [k for k, v in TEMPLATE_MAP.items() if v == template_id][0]
    output.append(f"PLAY [{t_name}] ************************************************************")
    output.append("")
    output.append("TASK [Gathering Facts] *********************************************************")
    
    results = {}
    for server in FLEET_SERVERS:
        rand = random.random()
        if rand < 0.95:
            results[server] = "ok"
            output.append(f"ok: [{server}]")
        else:
            results[server] = "failed"
            output.append(f"fatal: [{server}]: FAILED! => {{\"msg\": \"Task failed on this node\"}}")

    output.append("")
    output.append(f"TASK [{t_name} Logic] *******************************************************")
    for server, res in results.items():
        if res == "ok": output.append(f"changed: [{server}]")

    output.append("")
    summary = {
        "total": len(FLEET_SERVERS),
        "successful": sum(1 for r in results.values() if r == "ok"),
        "failed": sum(1 for r in results.values() if r == "failed")
    }
    
    output.append(f"ok: [localhost] => {{")
    output.append(f"    \"msg\": \"{t_name} process completed.\",")
    output.append(f"    \"summary\": {json.dumps(summary, indent=8)}")
    output.append(f"}}")
    output.append("")
    output.append("PLAY RECAP *********************************************************************")
    for server in FLEET_SERVERS:
        res = results[server]
        output.append(f"{server:30} : ok=3    changed=1    unreachable=0    failed={1 if res=='failed' else 0}")
            
    return "\n".join(output)

@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'])
def get_job_stdout(job_id):
    job = jobs.get(job_id)
    if not job: return "Not found", 404
    
    template_id = job["template_id"]
    extra_vars = job["extra_vars"]
    hostname = extra_vars.get('hostname') or extra_vars.get('hostlist', 'unknown-host')

    if template_id in [110, 111, 112, 113]:
        return generate_fleet_stdout(template_id, job["status"])
    
    if template_id == 126:
        # Get Server Info
        hostlist = extra_vars.get('hostlist', '')
        requested_hosts = [h.strip() for h in hostlist.split(',') if h.strip()]
        result = {}
        for h in requested_hosts:
            result[h] = INVENTORY_DATA.get(h, {"is_ha": False, "planned_reboot": False})
        
        return f"""
PLAY [Get Server Info] *********************************************************
TASK [Output Inventory] ********************************************************
ok: [localhost] => {{
    "msg": "Inventory data retrieved",
    "inventory": {json.dumps(result, indent=8)}
}}
PLAY RECAP *********************************************************************
localhost                      : ok=2    changed=0    unreachable=0    failed=0
"""

    msg = f"Operation completed on {hostname}"
    if template_id == 110:
        # Add reboot_required to patch fleet logic (simulated)
        reboot_req = random.random() < 0.3
        msg = f"Patching completed on {hostname}. Reboot required: {str(reboot_req).lower()}"
    elif template_id == 114: msg = f"Node {hostname} put in STANDBY mode."
    elif template_id == 115: msg = f"Node {hostname} taken out of STANDBY mode."
    elif template_id == 120: msg = "Health Check: PASS"
    elif template_id == 121: msg = "CIB Upgrade Successful"
    elif template_id == 122: 
        mode = "enabled" if extra_vars.get("enable", True) else "disabled"
        msg = f"Maintenance mode {mode} for cluster."
    elif template_id == 123: msg = f"Resource {extra_vars.get('resource_id')} moved to {extra_vars.get('target_node')}."
    elif template_id == 124: msg = f"Constraints cleared for resource {extra_vars.get('resource_id')}."
    elif template_id == 125: msg = "Location Constraints: p_fs_app (node-01), p_vip_app (node-01). No other constraints."
    
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

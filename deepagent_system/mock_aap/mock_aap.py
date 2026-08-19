from flask import Flask, request, jsonify
import random
import time
import logging
import sys
import json
from datetime import datetime

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

# 10 HA Clusters with 2 nodes and dedicated resource groups
HA_CLUSTERS = {
    f"ha-cluster-{i:02d}": {
        "nodes": [f"rhel-ha-{i:02d}-node1", f"rhel-ha-{i:02d}-node2"],
        "resource_groups": [f"rg_app_{i:02d} (vip_app_{i:02d}, fs_app_{i:02d}, svc_app_{i:02d})"]
    }
    for i in range(1, 11)
}

ALL_HA_NODES = [node for c in HA_CLUSTERS.values() for node in c["nodes"]]
ALL_FLEET_SERVERS = [f"rhel-prod-{i:02d}" for i in range(1, 11)]

# State tracking for console recovery
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

jobs = {}

def get_iso_now():
    return datetime.utcnow().isoformat() + "Z"

def parse_hostlist(extra_vars):
    raw = extra_vars.get('hostlist') or extra_vars.get('hostname') or extra_vars.get('target_hosts') or ''
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        # Check if cluster names provided
        tokens = [h.strip() for h in raw.split(',') if h.strip()]
        expanded = []
        for t in tokens:
            if t in HA_CLUSTERS:
                expanded.extend(HA_CLUSTERS[t]["nodes"])
            else:
                expanded.append(t)
        return expanded
    return ALL_HA_NODES

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
                "description": f"Batch automation mock for {name}",
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
    
    if template_id in [107, 128]: # VMware Reset or Console Power On
        h = extra_vars.get('hostname') or extra_vars.get('vm_name') or extra_vars.get('hostlist', '')
        if h:
            CONSOLE_RECOVERED_HOSTS.add(str(h))

    jobs[job_id] = {
        "id": job_id,
        "status": "successful",
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
        "name": "Simulated Batch Job",
        "status": current_status,
        "failed": False,
        "started": job["created"],
        "finished": get_iso_now() if current_status != "running" else None,
        "job_template": job["template_id"],
        "extra_vars": json.dumps(job["extra_vars"])
    })

@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'])
def get_job_stdout(job_id):
    job = jobs.get(job_id)
    if not job:
        return "Not found", 404
    
    template_id = job["template_id"]
    extra_vars = job["extra_vars"]
    targets = parse_hostlist(extra_vars)

    # 1. PCS Cluster Health Check (Batch across clusters)
    if template_id == 120:
        lines = ["PLAY [PCS Cluster Health Check - Batch Validation] **************************"]
        lines.append("TASK [Inspect Pacemaker Quorum & Resource Groups] ******************************")
        for i in range(1, 11):
            c_name = f"ha-cluster-{i:02d}"
            n1 = f"rhel-ha-{i:02d}-node1"
            n2 = f"rhel-ha-{i:02d}-node2"
            rg = f"rg_app_{i:02d}"
            lines.append(f"ok: [{c_name}] => {{")
            lines.append(f"    \"cluster\": \"{c_name}\",")
            lines.append(f"    \"quorum\": \"QUORATE (2/2 nodes active: {n1}, {n2})\",")
            lines.append(f"    \"stonith\": \"ENABLED (fence_ipmilan active)\",")
            lines.append(f"    \"resource_groups\": [\"{rg} -> active on {n1}\"],")
            lines.append(f"    \"health_status\": \"PASS\"")
            lines.append("}")
        lines.append("\nPLAY RECAP *********************************************************************")
        lines.append("localhost                      : ok=10   changed=0    unreachable=0    failed=0")
        return "\n".join(lines)

    # 2. PCS Node Standby (Batch Evacuation)
    if template_id == 114:
        lines = [f"PLAY [PCS Node Standby - Batch Evacuation ({len(targets)} Nodes)] *******************"]
        lines.append("TASK [Put Target Nodes in Standby & Evacuate Resources] *************************")
        for t in targets:
            lines.append(f"changed: [{t}] => {{ \"msg\": \"Node {t} put in STANDBY. Resources failed over to peer node.\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 3. Patch Fleet (Batch DNF Security Updates)
    if template_id == 110:
        lines = [f"PLAY [Patch Fleet - Batch DNF Package Updates ({len(targets)} Servers)] ***********"]
        lines.append("TASK [Apply Security & Bugfix Packages via DNF] *********************************")
        for t in targets:
            lines.append(f"changed: [{t}] => {{ \"packages_updated\": 14, \"reboot_required\": true }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=3    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 4. Reboot Fleet / Host (Batch Managed Reboot)
    if template_id in [102, 111]:
        lines = [f"PLAY [Managed Fleet Reboot - ({len(targets)} Servers)] **************************"]
        lines.append("TASK [Issue Managed System Reboot] **********************************************")
        for t in targets:
            elapsed = 38 if "node1" in t or "prod-01" in t else 44
            lines.append(f"changed: [{t}] => {{ \"msg\": \"Reboot completed. Elapsed: {elapsed} seconds.\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 5. Check Host Online (Batch TCP/SSH Port 22 Verification)
    if template_id == 127:
        lines = [f"PLAY [Check Host Online - Batch Verification ({len(targets)} Servers)] *********"]
        lines.append("TASK [Verify SSH Port 22 Responsiveness] ***************************************")
        for t in targets:
            if "node1" in t and "03" in t and t not in CONSOLE_RECOVERED_HOSTS:
                lines.append(f"failed: [{t}] => {{ \"online\": false, \"stage\": \"Reboot\", \"error\": \"SSH Port 22 timeout after reboot - host unresponsive.\" }}")
            else:
                method = "Console Recovered" if t in CONSOLE_RECOVERED_HOSTS else "Standard SSH"
                lines.append(f"ok: [{t}] => {{ \"online\": true, \"uptime\": \"55s\", \"boot_method\": \"{method}\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=0    unreachable=0    failed=0")
        return "\n".join(lines)

    # 6. Out-of-band Console Power On / VMware Reset
    if template_id in [107, 128]:
        lines = [f"PLAY [Out-of-Band Console Power Recovery ({len(targets)} Targets)] ****************"]
        lines.append("TASK [Trigger IPMI / Console Hard Power-On] *************************************")
        for t in targets:
            CONSOLE_RECOVERED_HOSTS.add(t)
            lines.append(f"changed: [{t}] => {{ \"msg\": \"Console power-on triggered. Node booted successfully into OS.\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 7. PCS Node Unstandby (Batch Reintegration)
    if template_id == 115:
        lines = [f"PLAY [PCS Node Unstandby - Batch Reintegration ({len(targets)} Nodes)] *************"]
        lines.append("TASK [Clear Standby & Reintegrate Nodes] ****************************************")
        for t in targets:
            lines.append(f"changed: [{t}] => {{ \"msg\": \"Node {t} unstandby completed. Cluster quorate and balanced.\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 8. Send Email Notification
    if template_id == 109:
        recipient = extra_vars.get('recipient', 'admin@enterprise.local')
        subj = extra_vars.get('subject', '[SRE Report] Maintenance Completed')
        return f"""
PLAY [Send Email Notification] *************************************************
TASK [Dispatch Maintenance Report via SMTP] ************************************
ok: [localhost] => {{
    "msg": "Notification email successfully dispatched to {recipient}.",
    "subject": "{subj}",
    "status": "delivered"
}}
PLAY RECAP *********************************************************************
localhost                      : ok=2    changed=1    unreachable=0    failed=0
"""

    # Generic Fallback
    return f"""
PLAY [Generic Job] *************************************************************
ok: [localhost] => {{ "msg": "Operation completed on batch targets." }}
PLAY RECAP *********************************************************************
localhost                      : ok=1    changed=0    unreachable=0    failed=0
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

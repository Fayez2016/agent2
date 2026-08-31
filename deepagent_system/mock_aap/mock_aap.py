from flask import Flask, request, jsonify
import random
import time
import logging
import sys
import json
import re
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('aap_server.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AAP-Simulation-Engine")

app = Flask(__name__)

# State tracking for dynamic simulation
CONSOLE_RECOVERED_HOSTS = set()
PCS_FIXED_HOSTS = set()

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

def extract_host_tokens(raw_input) -> list:
    """Universally parses any input format (comma-delimited, space-delimited, list, JSON) into distinct host tokens."""
    if not raw_input:
        return ["srv-generic-01"]
    if isinstance(raw_input, list):
        return [str(x).strip() for x in raw_input if str(x).strip()]
    
    cleaned = str(raw_input).strip()
    tokens = re.split(r'[,\s]+', cleaned)
    tokens = [t.strip() for t in tokens if t.strip() and t.lower() not in ["and", "to", "across", "hosts", "clusters", "the"]]
    return tokens if tokens else ["srv-generic-01"]

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
                "description": f"Dynamic SRE infrastructure simulation for {name}",
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
    
    # 1. Record console recovery for target hosts
    if template_id in [107, 128]: # VMware Reset or Console Power On
        raw = extra_vars.get('hostlist') or extra_vars.get('hostname') or extra_vars.get('vm_name') or ''
        for h in extract_host_tokens(raw):
            CONSOLE_RECOVERED_HOSTS.add(h)
            logger.info(f"Console Recovery recorded for host: {h}")

    # 2. Record PCS cluster fixes
    if template_id == 105: # Fix PCS Cluster
        raw = extra_vars.get('hostlist') or extra_vars.get('hostname') or ''
        for h in extract_host_tokens(raw):
            PCS_FIXED_HOSTS.add(h)
            logger.info(f"PCS Cluster Fix recorded for host: {h}")

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
    current_status = "running" if elapsed < 0.1 else job["status"]
    
    return jsonify({
        "id": job_id,
        "type": "job",
        "url": f"/api/v2/jobs/{job_id}/",
        "name": "Dynamic Simulation Job",
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
    raw_targets = extra_vars.get('hostlist') or extra_vars.get('hostname') or extra_vars.get('target_hosts') or ''
    targets = extract_host_tokens(raw_targets)

    # 1. PCS Cluster Health Check
    if template_id == 120:
        # Expand 10 clusters if generic or range specified
        if any("10" in t or "all" in t.lower() or t == "srv-generic-01" or "cluster1" in t.lower() for t in targets):
            cluster_names = [f"cluster{i}" for i in range(1, 11)]
        else:
            cluster_names = targets

        lines = [f"PLAY [PCS Cluster Health Check - Dynamic Inspection ({len(cluster_names)} Clusters)] *********"]
        lines.append("TASK [Inspect Pacemaker Quorum, STONITH & Resource Groups] ********************")
        for c in cluster_names:
            c_clean = c.replace("-", "_").lower()
            c_num = "".join(filter(str.isdigit, c_clean)) or "1"
            n1 = f"ha_cluster{c_num}_node1"
            n2 = f"ha_cluster{c_num}_node2"
            c_label = f"ha_cluster{c_num}"
            rg = f"rg_ha_cluster{c_num}"
            
            lines.append(f"ok: [{c_label}] => {{")
            lines.append(f"    \"cluster\": \"{c_label}\",")
            lines.append(f"    \"quorum\": \"QUORATE (Active members: {n1}, {n2})\",")
            lines.append(f"    \"active_nodes\": [\"{n1}\", \"{n2}\"],")
            lines.append(f"    \"wave_1_primary\": \"{n1}\",")
            lines.append(f"    \"wave_2_secondary\": \"{n2}\",")
            lines.append(f"    \"stonith\": \"ENABLED (fence_ipmilan active)\",")
            lines.append(f"    \"resource_groups\": [\"{rg} (vip_{c_num}, fs_{c_num}, app_{c_num}) -> active on {n1}\"],")
            lines.append(f"    \"health_status\": \"PASS\"")
            lines.append("}")
        lines.append("\nPLAY RECAP *********************************************************************")
        lines.append(f"localhost                      : ok={len(cluster_names)}   changed=0    unreachable=0    failed=0")
        return "\n".join(lines)

    # 2. PCS Node Standby
    if template_id == 114:
        lines = [f"PLAY [PCS Node Standby - Evacuation ({len(targets)} Nodes)] **********************"]
        lines.append("TASK [Set Standby State & Trigger Resource Failover] ***************************")
        for t in targets:
            lines.append(f"changed: [{t}] => {{ \"node\": \"{t}\", \"state\": \"STANDBY\", \"msg\": \"Resources migrated to active peer.\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 3. Patch Fleet (Simulate Clean Updates vs DNF Transaction Failure)
    if template_id == 110:
        lines = [f"PLAY [Patch Fleet - DNF Package Updates ({len(targets)} Servers)] ****************"]
        lines.append("TASK [Apply Security & Enhancement Packages via DNF] ***************************")
        for t in targets:
            # Simulate failure if target has 'err', 'fail', 'dnf', or specifically simulated test targets 'cluster3_node1', 'ha_cluster3_node1', 'rhel-prod-04'
            is_patch_failure = any(k in t.lower() for k in ["err", "fail", "dnf", "pkg_fail", "cluster3_node1", "ha_cluster3_node1", "rhel-prod-04", "prod-04"])
            if is_patch_failure:
                lines.append(f"failed: [{t}] => {{ \"stage\": \"Patching\", \"error\": \"DNF Transaction Error: GPG key verification failed or package dependency conflict on {t}.\", \"reboot_required\": false }}")
            else:
                pkgs = random.randint(12, 28)
                lines.append(f"changed: [{t}] => {{ \"packages_updated\": {pkgs}, \"reboot_required\": true, \"status\": \"applied\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            is_patch_failure = any(k in t.lower() for k in ["err", "fail", "dnf", "pkg_fail", "cluster3_node1", "ha_cluster3_node1", "rhel-prod-04", "prod-04"])
            if is_patch_failure:
                lines.append(f"{t:30} : ok=1    changed=0    unreachable=0    failed=1")
            else:
                lines.append(f"{t:30} : ok=3    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 4. Managed Reboot
    if template_id in [102, 111]:
        lines = [f"PLAY [Managed Fleet Reboot - ({len(targets)} Servers)] **************************"]
        lines.append("TASK [Issue Managed System Reboot & Await Connection] ***************************")
        for t in targets:
            CONSOLE_RECOVERED_HOSTS.discard(t)
            elapsed = random.randint(32, 48)
            lines.append(f"changed: [{t}] => {{ \"msg\": \"Reboot completed cleanly.\", \"elapsed_sec\": {elapsed} }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 5. Check Host Online (Simulates Clean Online vs Soft-Hang)
    if template_id == 127:
        lines = [f"PLAY [Check Host Online - TCP Port 22 Verification ({len(targets)} Targets)] ****"]
        lines.append("TASK [Probe SSH Port 22 & Validate OS Uptime] **********************************")
        for t in targets:
            # Simulate a soft-hang on hosts with 'hang', 'cluster7_node1', 'ha_cluster7_node1', or 'rhel-prod-08' before console recovery
            is_explicit_hang = ("hang" in t.lower() or "cluster7_node1" in t.lower() or "ha_cluster7_node1" in t.lower() or "rhel-prod-08" in t.lower() or "prod-08" in t.lower()) and (t not in CONSOLE_RECOVERED_HOSTS)
            if is_explicit_hang:
                lines.append(f"failed: [{t}] => {{ \"online\": false, \"stage\": \"Reboot Verification\", \"error\": \"SSH Port 22 connection timed out (Kernel soft hang detected on {t}).\" }}")
            else:
                method = "Console Recovered (IPMI)" if t in CONSOLE_RECOVERED_HOSTS else "Standard SSH"
                uptime = f"{random.randint(40, 90)}s"
                lines.append(f"ok: [{t}] => {{ \"online\": true, \"uptime\": \"{uptime}\", \"boot_method\": \"{method}\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            is_hang = ("hang" in t.lower() or "cluster7_node1" in t.lower() or "ha_cluster7_node1" in t.lower() or "rhel-prod-08" in t.lower() or "prod-08" in t.lower()) and (t not in CONSOLE_RECOVERED_HOSTS)
            if is_hang:
                lines.append(f"{t:30} : ok=1    changed=0    unreachable=1    failed=1")
            else:
                lines.append(f"{t:30} : ok=2    changed=0    unreachable=0    failed=0")
        return "\n".join(lines)

    # 6. Out-of-Band Console Power On / VMware Reset
    if template_id in [107, 128]:
        lines = [f"PLAY [Out-of-Band Console Power On / Hardware Cycle ({len(targets)} Targets)] ***"]
        lines.append("TASK [Issue Hardware Power-On via IPMI / Out-of-Band Interface] ****************")
        for t in targets:
            CONSOLE_RECOVERED_HOSTS.add(t)
            lines.append(f"changed: [{t}] => {{ \"msg\": \"Power-on signal issued via IPMI. Hardware rebooted into OS successfully.\", \"status\": \"recovered\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 7. PCS Cluster Fix / Cleanup
    if template_id == 105:
        lines = [f"PLAY [Fix PCS Cluster Resources ({len(targets)} Targets)] ************************"]
        lines.append("TASK [Clear Failcounts & Rebalance Resource Groups] *****************************")
        for t in targets:
            PCS_FIXED_HOSTS.add(t)
            lines.append(f"changed: [{t}] => {{ \"msg\": \"Resource failcounts cleared and constraints rebalanced.\", \"status\": \"cleaned\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 8. PCS Node Unstandby
    if template_id == 115:
        lines = [f"PLAY [PCS Node Unstandby - Reintegration ({len(targets)} Nodes)] *****************"]
        lines.append("TASK [Clear Standby State & Restore Cluster Quorum] *****************************")
        for t in targets:
            lines.append(f"changed: [{t}] => {{ \"node\": \"{t}\", \"state\": \"UNSTANDBY\", \"msg\": \"Node reintegrated into cluster successfully. Quorum balanced.\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 9. PCS Status Post-Check
    if template_id == 108:
        lines = [f"PLAY [PCS Status Post-Check ({len(targets)} Clusters)] **************************"]
        lines.append("TASK [Inspect Final Quorum & Balanced Resource Groups] *************************")
        for t in targets:
            lines.append(f"ok: [{t}] => {{ \"cluster\": \"{t}\", \"quorum\": \"QUORATE (All members online)\", \"resource_groups\": \"Healthy & Balanced\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=0    unreachable=0    failed=0")
        return "\n".join(lines)

    # 10. Send Email Notification
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
PLAY [Generic Operation on {len(targets)} Targets] ******************************
ok: [localhost] => {{ "msg": "Operation completed on all target hosts." }}
PLAY RECAP *********************************************************************
localhost                      : ok=1    changed=0    unreachable=0    failed=0
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

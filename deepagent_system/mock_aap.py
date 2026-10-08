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
    "HA Rolling Update": 129,
    "Get Maintenance Window Hosts": 130,
    "Unified Fleet Patch": 131
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

@app.route('/api/v2/ping', methods=['GET'], strict_slashes=False)
@app.route('/api/v2/ping/', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/ping', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/ping/', methods=['GET'], strict_slashes=False)
def ping_aap():
    return jsonify({"status": "ok", "version": "2.4.0"})

@app.route('/api/v2/job_templates', methods=['GET'], strict_slashes=False)
@app.route('/api/v2/job_templates/', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/job_templates', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/job_templates/', methods=['GET'], strict_slashes=False)
def get_job_templates():
    name = request.args.get('name')
    if name:
        template_id = TEMPLATE_MAP.get(name, 200)
        results = [
            {
                "id": template_id,
                "type": "job_template",
                "url": f"/api/controller/v2/job_templates/{template_id}/",
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
    else:
        results = []
        for t_name, t_id in TEMPLATE_MAP.items():
            results.append({
                "id": t_id,
                "type": "job_template",
                "url": f"/api/controller/v2/job_templates/{t_id}/",
                "name": t_name,
                "description": f"Dynamic SRE infrastructure simulation for {t_name}",
                "job_type": "run",
                "inventory": 1,
                "project": 1,
                "playbook": f"{t_name.lower().replace(' ', '_')}.yml",
                "created": "2026-01-01T12:00:00.000000Z",
                "modified": get_iso_now()
            })
    
    return jsonify({
        "count": len(results),
        "next": None,
        "previous": None,
        "results": results
    })

@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'], strict_slashes=False)
@app.route('/api/v2/job_templates/<int:template_id>/launch', methods=['POST'], strict_slashes=False)
@app.route('/api/controller/v2/job_templates/<int:template_id>/launch/', methods=['POST'], strict_slashes=False)
@app.route('/api/controller/v2/job_templates/<int:template_id>/launch', methods=['POST'], strict_slashes=False)
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
        "url": f"/api/controller/v2/jobs/{job_id}/"
    }), 201

@app.route('/api/v2/jobs/<int:job_id>/', methods=['GET'], strict_slashes=False)
@app.route('/api/v2/jobs/<int:job_id>', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>/', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>', methods=['GET'], strict_slashes=False)
def get_job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"detail": "Not found."}), 404
    
    elapsed = time.time() - job["start_time"]
    current_status = "running" if elapsed < 1.5 else job["status"]
    
    return jsonify({
        "id": job_id,
        "type": "job",
        "url": f"/api/controller/v2/jobs/{job_id}/",
        "name": "Dynamic Simulation Job",
        "status": current_status,
        "failed": False,
        "started": job["created"],
        "finished": get_iso_now() if current_status != "running" else None,
        "job_template": job["template_id"],
        "extra_vars": json.dumps(job["extra_vars"])
    })

@app.route('/api/v2/jobs/<int:job_id>/job_host_summaries/', methods=['GET'], strict_slashes=False)
@app.route('/api/v2/jobs/<int:job_id>/job_host_summaries', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>/job_host_summaries/', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>/job_host_summaries', methods=['GET'], strict_slashes=False)
def get_job_host_summaries(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"detail": "Not found."}), 404
    
    extra_vars = job.get("extra_vars", {})
    raw_targets = extra_vars.get('hostlist') or extra_vars.get('hostname') or extra_vars.get('target_hosts') or extra_vars.get('limit') or ''
    targets = extract_host_tokens(raw_targets)
    if not targets:
        # Default simulated fleet if limit was a generic group
        targets = [f"rhel-srv{i:02d}.internal" for i in range(1, 11)]

    results = []
    for idx, t in enumerate(targets):
        is_failed = ("err" in t.lower() or "fail" in t.lower() or "lock" in t.lower())
        results.append({
            "id": idx + 1,
            "failed": is_failed,
            "dark": False,
            "ok": 3 if not is_failed else 1,
            "changed": 2 if not is_failed else 0,
            "summary_fields": {
                "host": {"id": idx + 100, "name": t}
            }
        })

    return jsonify({
        "count": len(results),
        "results": results
    })

@app.route('/api/v2/jobs/<int:job_id>/job_events/', methods=['GET'], strict_slashes=False)
@app.route('/api/v2/jobs/<int:job_id>/job_events', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>/job_events/', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>/job_events', methods=['GET'], strict_slashes=False)
def get_job_events(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"detail": "Not found."}), 404

    extra_vars = job.get("extra_vars", {})
    raw_targets = extra_vars.get('hostlist') or extra_vars.get('hostname') or extra_vars.get('target_hosts') or extra_vars.get('limit') or ''
    targets = extract_host_tokens(raw_targets)

    results = []
    for t in targets:
        if "lock" in t.lower():
            results.append({
                "event": "runner_on_failed",
                "failed": True,
                "event_data": {
                    "host": t,
                    "task": "Stage 1: Apply OS Package Updates",
                    "res": {
                        "msg": "Failed to acquire DNF lock /var/run/yum.pid held by process PID 8122",
                        "rc": 1
                    }
                }
            })
        elif "reboot" in t.lower() or "hang" in t.lower():
            results.append({
                "event": "runner_on_failed",
                "failed": True,
                "event_data": {
                    "host": t,
                    "task": "Stage 4: Post-Reboot SSH Verification",
                    "res": {
                        "msg": "Timed out waiting for connection on port 22",
                        "rc": 1
                    }
                }
            })
        elif "err" in t.lower() or "fail" in t.lower():
            results.append({
                "event": "runner_on_failed",
                "failed": True,
                "event_data": {
                    "host": t,
                    "task": "Stage 1: Apply OS Package Updates",
                    "res": {
                        "msg": "Transaction test error: Conflicting package dependencies",
                        "rc": 1
                    }
                }
            })

    return jsonify({
        "count": len(results),
        "results": results
    })

@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'], strict_slashes=False)
@app.route('/api/v2/jobs/<int:job_id>/stdout', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>/stdout/', methods=['GET'], strict_slashes=False)
@app.route('/api/controller/v2/jobs/<int:job_id>/stdout', methods=['GET'], strict_slashes=False)
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
        lines = [f"PLAY [PCS Cluster Health Check - Dynamic Discovery ({len(targets)} Targets)] *********"]
        lines.append("TASK [Inspect Pacemaker Quorum, STONITH & Resource Groups] ********************")
        for t in targets:
            c_name = t if "cluster" in t else f"cluster-{t}"
            n1 = f"{t}-node1" if not ("node1" in t or "node2" in t) else t
            n2 = f"{t}-node2" if not ("node1" in t or "node2" in t) else f"{t}-peer"
            rg = f"rg_{t}"
            
            # Simulate degraded / warning resource state if explicitly specified or randomized
            has_failcount = ("fail" in t.lower() or "alert" in t.lower()) and (t not in PCS_FIXED_HOSTS)
            if has_failcount:
                lines.append(f"ok: [{t}] => {{")
                lines.append(f"    \"cluster\": \"{c_name}\",")
                lines.append(f"    \"members\": [\"{n1}\", \"{n2}\"],")
                lines.append(f"    \"wave_1_target\": \"{n1}\",")
                lines.append(f"    \"wave_2_target\": \"{n2}\",")
                lines.append(f"    \"quorum\": \"QUORATE (2/2 nodes active)\",")
                lines.append(f"    \"stonith\": \"ENABLED (fence_ipmilan active)\",")
                lines.append(f"    \"resource_groups\": [\"{rg} -> Degraded (Failcount: 1 on {n1})\"] ,")
                lines.append(f"    \"health_status\": \"WARNING - Failcount detected\"")
                lines.append("}")
            else:
                lines.append(f"ok: [{t}] => {{")
                lines.append(f"    \"cluster\": \"{c_name}\",")
                lines.append(f"    \"members\": [\"{n1}\", \"{n2}\"],")
                lines.append(f"    \"wave_1_target\": \"{n1}\",")
                lines.append(f"    \"wave_2_target\": \"{n2}\",")
                lines.append(f"    \"quorum\": \"QUORATE (Active members: {n1}, {n2})\",")
                lines.append(f"    \"stonith\": \"ENABLED (fence_ipmilan active)\",")
                lines.append(f"    \"resource_groups\": [\"{rg} (vip_{t}, fs_{t}, app_{t}) -> active on {n1}\"],")
                lines.append(f"    \"health_status\": \"PASS\"")
                lines.append("}")
        lines.append("\nPLAY RECAP *********************************************************************")
        lines.append(f"localhost                      : ok={len(targets)}   changed=0    unreachable=0    failed=0")
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

    # 3. Patch Fleet / Unified Fleet Patch (Simulate Clean Updates vs Failures)
    if template_id in [110, 131]:
        lines = [f"PLAY [Enterprise Linux Fleet Patching Workflow ({len(targets)} Servers)] ****************"]
        lines.append("TASK [Stage 1: Apply OS Package Updates] **************************************")
        for t in targets:
            if "lock" in t.lower():
                lines.append(f"failed: [{t}] => {{ \"stage\": \"Patching\", \"error\": \"Failed to acquire DNF lock /var/run/yum.pid held by process PID 8122\" }}")
            elif "err" in t.lower() or "fail" in t.lower():
                lines.append(f"failed: [{t}] => {{ \"stage\": \"Patching\", \"error\": \"DNF Transaction Error: GPG key verification failed or package dependency conflict.\" }}")
            else:
                pkgs = random.randint(12, 28)
                lines.append(f"changed: [{t}] => {{ \"packages_updated\": {pkgs}, \"status\": \"applied\" }}")
        
        lines.append("\nTASK [Stage 2: Check If Reboot Required] *************************************")
        for t in targets:
            rc = 1 if ("reboot" in t.lower() or "hang" in t.lower() or not ("norbt" in t.lower())) else 0
            lines.append(f"ok: [{t}] => {{ \"rc\": {rc}, \"reboot_required\": {str(rc == 1).lower()} }}")

        lines.append("\nTASK [Stage 3: Rolling Reboot When Required] *********************************")
        for t in targets:
            if "hang" in t.lower():
                lines.append(f"fatal: [{t}] => {{ \"msg\": \"Reboot command timed out after 600s\" }}")
            else:
                lines.append(f"changed: [{t}] => {{ \"msg\": \"Reboot completed successfully\" }}")

        lines.append("\nTASK [Stage 4: Post-Reboot SSH Verification] **********************************")
        for t in targets:
            if "hang" in t.lower():
                lines.append(f"fatal: [{t}] => {{ \"msg\": \"Timed out waiting for connection on port 22\" }}")
            else:
                lines.append(f"ok: [{t}] => {{ \"port\": 22, \"state\": \"started\" }}")

        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            has_fail = ("err" in t.lower() or "fail" in t.lower() or "lock" in t.lower() or "hang" in t.lower())
            lines.append(f"{t:30} : ok=4    changed=2    unreachable=0    failed={1 if has_fail else 0}")
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
            # Simulate a soft-hang if host has 'hang' in name AND not yet console recovered
            is_soft_hang = ("hang" in t.lower()) and (t not in CONSOLE_RECOVERED_HOSTS)
            if is_soft_hang:
                lines.append(f"failed: [{t}] => {{ \"online\": false, \"stage\": \"Reboot Verification\", \"error\": \"SSH Port 22 connection timed out (Kernel soft hang detected).\" }}")
            else:
                method = "Console Recovered (IPMI)" if t in CONSOLE_RECOVERED_HOSTS else "Standard SSH"
                uptime = f"{random.randint(40, 90)}s"
                lines.append(f"ok: [{t}] => {{ \"online\": true, \"uptime\": \"{uptime}\", \"boot_method\": \"{method}\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
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

    # 10. Get Server Info (Template 126 - Returns Batch Server Telemetry, OOBM & vCenter metadata)
    if template_id == 126:
        lines = [f"PLAY [Get Server Info & Telemetry ({len(targets)} Targets)] ********************"]
        lines.append("TASK [Gather Server Facts, OOBM IP & Hypervisor Metadata] **********************")
        for t in targets:
            is_vm = not ("bm" in t.lower() or "bare" in t.lower() or "phys" in t.lower())
            oobm_ip = f"10.20.30.{random.randint(10, 250)}"
            vm_name = t if is_vm else "N/A"
            lines.append(f"ok: [{t}] => {{")
            lines.append(f"    \"host\": \"{t}\",")
            lines.append(f"    \"is_virtual\": {str(is_vm).lower()},")
            lines.append(f"    \"oobm_ip\": \"{oobm_ip}\",")
            lines.append(f"    \"oobm_protocol\": \"redfish_ilo\",")
            lines.append(f"    \"vcenter_vm_name\": \"{vm_name}\",")
            lines.append(f"    \"status\": \"inventory_resolved\"")
            lines.append("}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=0    unreachable=0    failed=0")
        return "\n".join(lines)

    # 11. Send Email Notification
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

    # 11. Get Maintenance Window Hosts
    if template_id == 130:
        return """
PLAY [Discover Maintenance Window Target Hosts] ********************************
TASK [Filter Inventory by Maintenance Window & Role Tag] **********************
ok: [localhost] => {
    "msg": "Maintenance Window Active. Discovered eligible hosts.",
    "hosts": ["ha_cluster01_node1", "ha_cluster01_node2", "rhel-app-srv01", "rhel-db-srv02"],
    "window_tag": "PRODUCTION_WAVE_1",
    "status": "active"
}
PLAY RECAP *********************************************************************
localhost                      : ok=2    changed=0    unreachable=0    failed=0
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

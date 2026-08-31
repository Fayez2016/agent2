import json
import logging
import random
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from flask import Flask, request, jsonify

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MockAAPServer")

app = Flask(__name__)

# State trackers
jobs = {}
job_counter = 1000
CONSOLE_RECOVERED_HOSTS = set()
PCS_FIXED_HOSTS = set()

def get_iso_now():
    return datetime.now(timezone.utc).isoformat()

def extract_host_tokens(raw_str):
    if not raw_str:
        return []
    import re
    return [t.strip() for t in re.split(r'[\s,;|]+', str(raw_str)) if t.strip()]

def try_send_real_smtp_email(recipient: str, subject: str, body: str) -> bool:
    """Attempts direct SMTP transmission if host network allows port 25/587."""
    try:
        msg = MIMEMultipart()
        msg["From"] = "deepagent-sre@enterprise.local"
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        smtp_server = os.getenv("SMTP_SERVER", "localhost")
        smtp_port = int(os.getenv("SMTP_PORT", "25"))
        
        with smtplib.SMTP(smtp_server, smtp_port, timeout=2.0) as server:
            server.send_message(msg)
            logger.info(f"Real SMTP email dispatched to {recipient} via {smtp_server}:{smtp_port}")
            return True
    except Exception as e:
        logger.info(f"SMTP delivery direct note: {e} (Simulated Mock AAP delivery logged for {recipient})")
        return False

# 10 Clusters Dynamic Registry
TOPOLOGY_CLUSTERS = [f"ha_cluster{i}" for i in range(1, 11)]

JOB_TEMPLATES = [
    {"id": 101, "name": "PCS Node Standby"},
    {"id": 102, "name": "PCS Node Unstandby"},
    {"id": 103, "name": "PCS Cluster Stop"},
    {"id": 104, "name": "PCS Cluster Start"},
    {"id": 105, "name": "Fix PCS Cluster"},
    {"id": 106, "name": "Expand Filesystem"},
    {"id": 107, "name": "Console Power On"},
    {"id": 108, "name": "PCS Status"},
    {"id": 109, "name": "Send Email Notification"},
    {"id": 110, "name": "Patch Fleet"},
    {"id": 111, "name": "Reboot Fleet"},
    {"id": 112, "name": "PCS Maintenance Mode"},
    {"id": 113, "name": "PCS Resource Move"},
    {"id": 114, "name": "PCS Resource Clear"},
    {"id": 115, "name": "Install Package"},
    {"id": 116, "name": "PCS Cluster Disable"},
    {"id": 117, "name": "PCS Cluster Enable"},
    {"id": 118, "name": "PCS Health Check"},
    {"id": 119, "name": "Limited Run Any Command"},
    {"id": 120, "name": "PCS CIB Upgrade"},
    {"id": 121, "name": "PCS Constraint List"},
    {"id": 126, "name": "Get Server Info"},
    {"id": 127, "name": "Check Host Online"},
    {"id": 128, "name": "VMware VM Reset"},
]

@app.route('/api/v2/job_templates', methods=['GET'])
def get_job_templates():
    name_filter = request.args.get('name')
    if name_filter:
        results = [jt for jt in JOB_TEMPLATES if jt['name'].lower() == name_filter.lower()]
    else:
        results = JOB_TEMPLATES
    return jsonify({"count": len(results), "results": results})

@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'])
def launch_job(template_id):
    global job_counter
    job_counter += 1
    job_id = job_counter
    
    data = request.get_json(silent=True) or {}
    extra_vars = data.get("extra_vars", {})
    if isinstance(extra_vars, str):
        try:
            extra_vars = json.loads(extra_vars)
        except Exception:
            extra_vars = {}

    # 1. Reset console recovery if node is rebooted
    if template_id in [102, 111]: # Managed Reboot
        raw = extra_vars.get('hostlist') or extra_vars.get('hostname') or ''
        for h in extract_host_tokens(raw):
            CONSOLE_RECOVERED_HOSTS.discard(h)
            logger.info(f"Reboot executed on {h}. Reset console state.")

    # 2. Record PCS cluster fixes
    if template_id == 105: # Fix PCS Cluster
        raw = extra_vars.get('hostlist') or extra_vars.get('hostname') or ''
        for h in extract_host_tokens(raw):
            PCS_FIXED_HOSTS.add(h)
            logger.info(f"PCS Cluster Fix recorded for host: {h}")

    # 3. Handle Send Email Notification (Real SMTP Attempt + Audit Log)
    if template_id == 109:
        recipient = extra_vars.get('recipient', 'fayez.soufyani@gmail.com')
        subj = extra_vars.get('subject', '[SRE Report] Deep Agent Execution Summary')
        body = extra_vars.get('body', 'Deep Agent SRE Maintenance Completed Successfully.')
        try_send_real_smtp_email(recipient, subj, body)

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
    
    extra_vars = job.get("extra_vars", {})
    raw_targets = extra_vars.get("hostlist") or extra_vars.get("hostname") or "localhost"
    targets = extract_host_tokens(raw_targets)
    if not targets:
        targets = ["localhost"]

    template_id = job.get("template_id")

    # 1. Dynamic 10-Cluster Discovery & Health Check
    if template_id == 118: # PCS Health Check
        clusters_to_check = targets if any("ha_cluster" in t or "cluster" in t for t in targets) else TOPOLOGY_CLUSTERS
        lines = [f"PLAY [10-Cluster Dynamic HA Health Check ({len(clusters_to_check)} Clusters)] **********"]
        lines.append("TASK [Inspect Corosync Membership, Quorum & STONITH Status] ********************")
        
        for c in clusters_to_check:
            c_clean = c.strip()
            num_match = "".join(filter(str.isdigit, c_clean))
            num = num_match if num_match else "1"
            n1 = f"ha_cluster{num}_node1"
            n2 = f"ha_cluster{num}_node2"
            
            lines.append(
                f"ok: [{c_clean}] => {{ \"cluster\": \"{c_clean}\", \"quorum\": \"QUORATE\", \"stonith\": \"enabled\", "
                f"\"nodes\": [\"{n1}\", \"{n2}\"], \"active_members\": [\"{n1}\", \"{n2}\"], \"primary_active_node\": \"{n1}\", \"secondary_node\": \"{n2}\" }}"
            )
        lines.append("\nPLAY RECAP *********************************************************************")
        for c in clusters_to_check:
            lines.append(f"{c:30} : ok=3    changed=0    unreachable=0    failed=0")
        return "\n".join(lines)

    # 2. Server Inventory Pre-Inspection
    if template_id == 126:
        lines = [f"PLAY [Discover Server Inventory ({len(targets)} Servers)] **********************"]
        lines.append("TASK [Gather Operating System Architecture, Kernel & Hardware Facts] ***********")
        for t in targets:
            lines.append(f"ok: [{t}] => {{ \"os\": \"Red Hat Enterprise Linux 9.4\", \"kernel\": \"5.14.0-427.el9.x86_64\", \"arch\": \"x86_64\", \"uptime_sec\": 864000, \"status\": \"healthy\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 3. Patch Fleet (Simulate Clean Updates vs DNF Transaction Failure)
    if template_id == 110:
        lines = [f"PLAY [Patch Fleet - DNF Package Updates ({len(targets)} Servers)] ****************"]
        lines.append("TASK [Apply Security & Enhancement Packages via DNF] ***************************")
        for t in targets:
            # Simulate failure if target has 'err', 'fail', 'dnf', 'cluster3_node1', 'ha_cluster3_node1', 'rhel-prod-04'
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
        lines = [f"PLAY [Fix PCS Cluster ({len(targets)} Nodes)] ************************************"]
        lines.append("TASK [Clear PCS Resource Failcounts & Re-enable Fencing] ***********************")
        for t in targets:
            lines.append(f"changed: [{t}] => {{ \"msg\": \"PCS resource failcounts cleared and fencing reintegrated.\", \"status\": \"healthy\" }}")
        lines.append("\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\n".join(lines)

    # 8. Node Standby / Unstandby
    if template_id in [101, 102]:
        action_str = "Standby" if template_id == 101 else "Unstandby"
        lines = [f"PLAY [PCS Node {action_str} ({len(targets)} Nodes)] ********************************"]
        lines.append(f"TASK [Place Nodes in {action_str} State] ****************************************")
        for t in targets:
            lines.append(f"changed: [{t}] => {{ \"node\": \"{t}\", \"state\": \"{action_str.lower()}\", \"resources_migrated\": true }}")
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
        recipient = extra_vars.get('recipient', 'fayez.soufyani@gmail.com')
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

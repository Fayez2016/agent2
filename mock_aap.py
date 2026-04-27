from flask import Flask, request, jsonify
import random
import time
import logging
import sys
import json

# Set up logging to both file and stdout for visibility
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

# List of 20 servers for fleet simulation
FLEET_SERVERS = [f"rhel-prod-{i:02d}.enterprise.local" for i in range(1, 21)]

@app.before_request
def log_request_info():
    logger.info("--- AAP REQUEST ---")
    logger.info(f"Method: {request.method}")
    logger.info(f"URL: {request.url}")
    
    try:
        if request.content_length and request.is_json:
            data = request.get_json(silent=True)
            logger.info(f"Body: {data}")
        else:
            data = request.get_data(as_text=True)
            if data:
                logger.info(f"Body: {data}")
            else:
                logger.info("Body: (empty)")
    except Exception as e:
        logger.info(f"Body: (could not log body: {e})")

@app.after_request
def log_response_info(response):
    logger.info("--- AAP RESPONSE ---")
    logger.info(f"Status: {response.status}")
    if response.mimetype in ['application/json', 'text/plain']:
        try:
            data = response.get_data(as_text=True)
            logger.info(f"Data: {data[:500]}{'...' if len(data) > 500 else ''}")
        except Exception:
            pass
    return response

# In-memory store for jobs
jobs = {}

# Template Name to ID mapping (Simulated)
TEMPLATE_MAP = {
    "Limited Run Any Command": 101,
    "Reboot Host": 102,
    "Install Package": 103,
    "Expand Filesystem": 104,
    "Fix PCS Cluster": 105,
    "Patching and Reboot": 106,
    "VMware VM Reset": 107,
    "PCS Status": 108,
    "Send Email Notification": 109
}

@app.route('/api/v2/job_templates', methods=['GET'])
def get_job_templates():
    name = request.args.get('name')
    template_id = TEMPLATE_MAP.get(name, random.randint(200, 300))
    return jsonify({
        "results": [{"id": template_id, "name": name}]
    })

@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'])
def launch_job(template_id):
    job_id = random.randint(10000, 99999)
    extra_vars = {}
    if request.is_json:
        data = request.get_json(silent=True)
        if data:
            extra_vars = data.get('extra_vars', {})
    
    status = "successful"
    # Logic for failure simulation in specific templates
    if template_id == 106: # Patching
        # 10% chance the whole job fails
        if random.random() < 0.1:
            status = "failed"
    
    # Store job info
    jobs[job_id] = {
        "status": status,
        "extra_vars": extra_vars,
        "template_id": template_id,
        "start_time": time.time()
    }
    
    logger.info(f"Launched job {job_id} for template {template_id}")
    return jsonify({"job": job_id}), 201

@app.route('/api/v2/jobs/<int:job_id>/', methods=['GET'])
def get_job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    elapsed = time.time() - job["start_time"]
    current_status = "running" if elapsed < 1.5 else job["status"]
    
    return jsonify({"status": current_status})

def generate_patching_stdout(job_id, extra_vars, final_status):
    output = []
    output.append("PLAY [Patch and Reboot RHEL Fleet] *******************************************")
    output.append("")
    output.append("TASK [Gathering Facts] *********************************************************")
    
    results = {}
    for server in FLEET_SERVERS:
        # Simulate individual server results
        rand = random.random()
        if rand < 0.85:
            results[server] = {"status": "ok", "msg": "Packages updated, reboot initiated"}
            output.append(f"ok: [{server}]")
        elif rand < 0.95:
            results[server] = {"status": "failed", "msg": "DNF repository connection timed out"}
            output.append(f"fatal: [{server}]: FAILED! => {{\"changed\": false, \"msg\": \"{results[server]['msg']}\"}}")
        else:
            results[server] = {"status": "unreachable", "msg": "SSH connection failed"}
            output.append(f"fatal: [{server}]: UNREACHABLE! => {{\"changed\": false, \"msg\": \"{results[server]['msg']}\"}}")

    output.append("")
    output.append("TASK [Apply Security Patches] *************************************************")
    for server, res in results.items():
        if res["status"] == "ok":
            output.append(f"changed: [{server}]")
    
    output.append("")
    output.append("TASK [Reboot systems] *********************************************************")
    for server, res in results.items():
        if res["status"] == "ok":
            output.append(f"changed: [{server}]")

    output.append("")
    output.append("TASK [Final Fleet Report] *****************************************************")
    
    summary = {
        "total": len(FLEET_SERVERS),
        "successful": sum(1 for r in results.values() if r["status"] == "ok"),
        "failed": sum(1 for r in results.values() if r["status"] == "failed"),
        "unreachable": sum(1 for r in results.values() if r["status"] == "unreachable"),
        "details": results
    }
    
    output.append(f"ok: [localhost] => {{")
    output.append(f"    \"msg\": \"Fleet patching completed. {summary['successful']}/{summary['total']} servers successful.\",")
    output.append(f"    \"summary\": {json.dumps(summary, indent=8)}")
    output.append(f"}}")
    output.append("")
    output.append("PLAY RECAP *********************************************************************")
    for server in FLEET_SERVERS:
        res = results[server]
        if res["status"] == "ok":
            output.append(f"{server:30} : ok=4    changed=2    unreachable=0    failed=0")
        elif res["status"] == "failed":
            output.append(f"{server:30} : ok=1    changed=0    unreachable=0    failed=1")
        else:
            output.append(f"{server:30} : ok=0    changed=0    unreachable=1    failed=0")
            
    return "\n".join(output)

@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'])
def get_job_stdout(job_id):
    job = jobs.get(job_id)
    if not job:
        return "Job not found", 404
    
    status = job["status"]
    template_id = job["template_id"]
    extra_vars = job["extra_vars"]
    hostname = extra_vars.get('hostname') or extra_vars.get('hostlist', 'unknown-host')

    # Template-specific Stdout
    if template_id == 106: # Patching Fleet
        return generate_patching_stdout(job_id, extra_vars, status)
    
    if template_id == 107: # VMware Reset
        msg = f"VM {hostname} hard reset signal sent via VMware API. VM is booting."
    elif template_id == 108: # PCS Status
        msg = f"Cluster Status for {hostname}: Online. Resources: p_fs_app (started), p_vip_app (started). Nodes: {hostname} (Online), node-02 (Online)."
    elif template_id == 109: # Send Email
        to = extra_vars.get("email_to", "admin@enterprise.com")
        msg = f"Notification email sent to {to} regarding operation on {hostname}"
    elif "agent_comand" in extra_vars:
        msg = f"Output of '{extra_vars['agent_comand']}' on {hostname}: success"
    else:
        msg = f"Operation completed successfully on {hostname}"

    output = f"""
PLAY [Enterprise Automation Job] **********************************************

TASK [Gathering Facts] *********************************************************
ok: [{hostname}]

TASK [Execute Business Logic] *************************************************
changed: [{hostname}]

TASK [Debug Result] ***********************************************************
ok: [{hostname}] => {{
    "msg": "{msg}",
    "status": "{status}"
}}

PLAY RECAP *********************************************************************
{hostname:30} : ok=3    changed=1    unreachable=0    failed=0
"""
    return output

if __name__ == '__main__':
    logger.info("Starting AAP API Server on port 5000...")
    app.run(host='0.0.0.0', port=5000)

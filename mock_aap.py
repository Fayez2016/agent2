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
            if data: logger.info(f"Body: {data}")
            else: logger.info("Body: (empty)")
    except Exception as e:
        logger.info(f"Body: (could not log body: {e})")

@app.after_request
def log_response_info(response):
    logger.info("--- AAP RESPONSE ---")
    logger.info(f"Status: {response.status}")
    return response

# In-memory store for jobs
jobs = {}

# Template Name to ID mapping
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
    "Send Email Notification": 109
}

@app.route('/api/v2/job_templates', methods=['GET'])
def get_job_templates():
    name = request.args.get('name')
    template_id = TEMPLATE_MAP.get(name, random.randint(200, 300))
    return jsonify({"results": [{"id": template_id, "name": name}]})

@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'])
def launch_job(template_id):
    job_id = random.randint(10000, 99999)
    extra_vars = {}
    if request.is_json:
        data = request.get_json(silent=True)
        if data: extra_vars = data.get('extra_vars', {})
    
    status = "successful"
    # Randomly fail patching or PCS checks to force agent orchestration/troubleshooting
    if template_id in [110, 112, 113] and random.random() < 0.15:
        status = "failed"
    
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
    if not job: return jsonify({"error": "Job not found"}), 404
    elapsed = time.time() - job["start_time"]
    current_status = "running" if elapsed < 1.0 else job["status"]
    return jsonify({"status": current_status})

def generate_fleet_stdout(template_id, status):
    output = []
    t_name = [k for k, v in TEMPLATE_MAP.items() if v == template_id][0]
    output.append(f"PLAY [{t_name}] ************************************************************")
    output.append("")
    output.append("TASK [Gathering Facts] *********************************************************")
    
    results = {}
    for server in FLEET_SERVERS:
        rand = random.random()
        if rand < 0.90 or template_id == 111: # Reboot fleet is very reliable in this sim
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
    if not job: return "Job not found", 404
    
    template_id = job["template_id"]
    extra_vars = job["extra_vars"]
    hostname = extra_vars.get('hostname') or extra_vars.get('hostlist', 'unknown-host')

    if template_id in [110, 111, 112, 113]:
        return generate_fleet_stdout(template_id, job["status"])
    
    # Existing single-host logic...
    msg = f"Operation completed on {hostname}"
    if template_id == 108: msg = "PCS Cluster is Healthy"
    
    return f"""
PLAY [Job] *********************************************************************
TASK [Action] ******************************************************************
ok: [{hostname}] => {{"msg": "{msg}"}}
PLAY RECAP *********************************************************************
{hostname:30} : ok=2    changed=0    unreachable=0    failed=0
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

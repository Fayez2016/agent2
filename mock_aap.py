from flask import Flask, request, jsonify
import random
import time
import logging
import sys

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

@app.before_request
def log_request_info():
    logger.info("--- AAP REQUEST ---")
    logger.info(f"Method: {request.method}")
    logger.info(f"URL: {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    # Safely log body without triggering 400 errors on empty JSON bodies
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
    # Only log text/json data, truncate if very long
    if response.mimetype in ['application/json', 'text/plain']:
        try:
            data = response.get_data(as_text=True)
            logger.info(f"Data: {data[:1000]}{'...' if len(data) > 1000 else ''}")
        except Exception:
            pass
    return response

# In-memory store for jobs
jobs = {}

@app.route('/api/v2/job_templates', methods=['GET'])
def get_job_templates():
    name = request.args.get('name')
    logger.info(f"Template lookup for: {name}")
    return jsonify({
        "results": [{"id": random.randint(100, 200), "name": name}]
    })

@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'])
def launch_job(template_id):
    job_id = random.randint(10000, 99999)
    extra_vars = {}
    if request.is_json:
        data = request.get_json(silent=True)
        if data:
            extra_vars = data.get('extra_vars', {})
    
    # Always succeed for testing unless specified
    status = "successful"
    
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
    
    # Simulate some processing time
    elapsed = time.time() - job["start_time"]
    current_status = "running" if elapsed < 1 else job["status"]
    
    return jsonify({"status": current_status})

@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'])
def get_job_stdout(job_id):
    job = jobs.get(job_id)
    if not job:
        return "Job not found", 404
    
    status = job["status"]
    extra_vars = job["extra_vars"]
    hostname = extra_vars.get('hostname') or extra_vars.get('hostlist', 'unknown-host')
    
    # Determine result message based on the input vars
    if "agent_comand" in extra_vars:
        cmd = extra_vars["agent_comand"]
        if cmd == "uptime":
            msg = f"Uptime for {hostname}: up 12 days, 4:20, 2 users, load average: 0.05, 0.03, 0.01"
        else:
            msg = f"Output of '{cmd}' on {hostname}: success"
    elif "package_name" in extra_vars:
        pkg = extra_vars["package_name"]
        msg = f"Package '{pkg}' successfully installed/updated on {hostname}"
    elif "mount_point" in extra_vars:
        mp = extra_vars["mount_point"]
        sz = extra_vars.get("size_gb", "??")
        msg = f"Filesystem {mp} on {hostname} successfully expanded to {sz}GB"
    elif "hostname" in extra_vars:
        msg = f"Operation completed successfully on {hostname}"
    else:
        msg = f"Ansible job completed with vars: {extra_vars}"

    output = f"""
PLAY [Ansible Job for Enterprise Automation] *********************************

TASK [Gathering Facts] *********************************************************
ok: [{hostname}]

TASK [Perform Automated Action] ***********************************************
changed: [{hostname}]

TASK [Report output to the agent using debug var] *****************************
ok: [{hostname}] => {{
    "msg": "{msg}",
    "status": "{status}"
}}

PLAY RECAP *********************************************************************
{hostname} : ok=3 changed=1 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0
"""
    return output

if __name__ == '__main__':
    logger.info("Starting AAP API Server on port 5000...")
    app.run(host='0.0.0.0', port=5000)

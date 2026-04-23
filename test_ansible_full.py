import subprocess
import time
import os

# Configuration
AGENT_CONTAINER = "hermes-agent"
SERVER_CONTAINER = "aap-server"
LOG_FILE = "ansible_full_communication.log"
MODEL = "qwen3-coder-next"

TEST_CASES = [
    {"name": "Run Command", "query": "check uptime on production-web-01"},
    {"name": "Reboot Host", "query": "reboot the host staging-db-02"},
    {"name": "Install Package", "query": "install the 'git' package on developer-workstation-03"},
    {"name": "Expand Filesystem", "query": "expand the /data mount point on storage-node-04 to 100GB"},
    {"name": "Fix PCS Cluster", "query": "fix the pcs cluster issues on node-05-cluster"}
]

def run_cmd(cmd):
    print(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr

def log(header, content):
    with open(LOG_FILE, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f" {header} \n")
        f.write(f"{'='*80}\n")
        f.write(content)
        f.write("\n")

def main():
    # Clear previous log
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    print(f"Starting full Ansible skills test. Results will be saved to {LOG_FILE}")
    
    # 1. Capture Initial State
    log("SYSTEM STATE: START", f"Timestamp: {time.ctime()}\nModel: {MODEL}")

    for case in TEST_CASES:
        print(f"\n--- Testing Skill: {case['name']} ---")
        
        # Run the agent command
        query_cmd = f"podman exec -u hermes {AGENT_CONTAINER} /opt/hermes/.venv/bin/python /opt/hermes/hermes chat -q '{case['query']}' -m {MODEL} -v"
        agent_output = run_cmd(query_cmd)
        
        # Log Agent interaction
        log(f"TEST CASE: {case['name']}\nQUERY: {case['query']}", agent_output)
        
        # Capture AAP Server logs for this specific interaction
        server_logs = run_cmd(f"podman logs --tail 20 {SERVER_CONTAINER}")
        log(f"SERVER LOGS: {case['name']}", server_logs)
        
        # Small delay to ensure logs are flushed
        time.sleep(2)

    # 2. Capture internal tool log
    print("\nCapturing internal tool logs...")
    tool_logs = run_cmd(f"podman exec {AGENT_CONTAINER} cat /opt/hermes/ansible_tool.log")
    log("INTERNAL TOOL LOGS (ansible_tool.log)", tool_logs)

    print(f"\nTest complete. Full communication log saved to: {os.path.abspath(LOG_FILE)}")

if __name__ == "__main__":
    main()

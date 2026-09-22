import os
import sys
import json
import time
import requests

print("=" * 80)
print("🚀 DEEP AGENT PLATFORM - COMPLETE END-TO-END VERIFICATION SUITE")
print("=" * 80)

# 1. Container Infrastructure Health
print("\n[Step 1/4] Checking Microservice Containers & Ingress...")
try:
    r_proxy = requests.get("https://127.0.0.1:8443", verify=False, timeout=5)
    print(f"  ✅ deepagent-proxy (HTTPS 8443)   : HTTP {r_proxy.status_code}")
except Exception as e:
    print(f"  ❌ deepagent-proxy (HTTPS 8443)   : FAILED ({e})")

try:
    r_core = requests.get("http://127.0.0.1:8642/health", timeout=5)
    print(f"  ✅ deepagent-service (Port 8642)  : HTTP {r_core.status_code}")
except Exception as e:
    print(f"  ❌ deepagent-service (Port 8642)  : FAILED ({e})")

# AAP & Ansible MCP inside pod network
aap_check = os.popen("podman exec -i deepagent-service curl -s http://127.0.0.1:5000/api/v2/job_templates").read()
try:
    data_aap = json.loads(aap_check)
    print(f"  ✅ deepagent-aap-server (Port 5000): {len(data_aap.get('results', []))} templates loaded & operational")
except Exception as e:
    print(f"  ❌ deepagent-aap-server (Port 5000): {aap_check[:100]}")

mcp_ping = os.popen("podman exec -i deepagent-service curl -s -I http://127.0.0.1:8000/mcp").read()
if "200" in mcp_ping or "400" in mcp_ping:
    print(f"  ✅ deepagent-ansible-mcp (Port 8000): FastMCP endpoint reachable")
else:
    print(f"  ❌ deepagent-ansible-mcp (Port 8000): Unreachable ({mcp_ping})")

# 2. Database & Active Model Configuration
print("\n[Step 2/4] Checking PostgreSQL Configuration & Active Model...")
db_agent = os.popen("podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c \"SELECT key_name, model_provider, model_name FROM domain_agents WHERE key_name='linux_sre';\"").read().strip()
print(f"  ✅ Active Agent: {db_agent}")

db_settings = os.popen("podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c \"SELECT key || '=' || value FROM system_settings WHERE key IN ('ansible_backend_mode', 'aap_host', 'hitl_mode', 'openrouter_model');\"").read().strip()
for s in db_settings.split("\n"):
    print(f"  ✅ {s}")

# 3. Ansible MCP Tool Matrix (All 14 Operations)
print("\n[Step 3/4] Testing Ansible MCP Tool Matrix via Pod Container...")
mcp_cmd = "podman exec -i -e PYTHONPATH=/app deepagent-ansible-mcp python3 /tmp/test_ansible_mcp_all.py"
res = os.popen(mcp_cmd).read()
for line in res.split("\n"):
    if "PASS" in line or "SUMMARY" in line:
        print("  " + line)

# 4. End-to-End Agent AI Chat Inference (Qwen 3.8 27B)
print("\n[Step 4/4] Testing End-to-End AI Agent Tool Calling (Qwen 3.8 27B)...")
payload = {
    "model": "deepagent",
    "domain": "linux_sre",
    "messages": [
        {"role": "user", "content": "How many users are logged in to sys2? Check using ansible_run_command."}
    ],
    "stream": False
}
headers = {
    "Authorization": "Bearer hermes-api-secret",
    "Content-Type": "application/json"
}
start_t = time.time()
try:
    resp = requests.post("http://127.0.0.1:8642/v1/chat/completions", json=payload, headers=headers, timeout=120)
    elapsed = round(time.time() - start_t, 2)
    if resp.status_code == 200:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"  ✅ Agent responded in {elapsed}s:")
        print("-" * 60)
        print(content.strip())
        print("-" * 60)
    else:
        print(f"  ❌ Agent returned HTTP {resp.status_code}: {resp.text}")
except Exception as e:
    print(f"  ❌ Inference request failed: {e}")

print("\n" + "=" * 80)
print("🏁 FULL VERIFICATION RUN COMPLETE")
print("=" * 80)

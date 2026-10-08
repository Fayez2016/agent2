#!/usr/bin/env bash
# ==============================================================================
# Script: check_integrity.sh
# Purpose: Comprehensive Diagnostic & Integrity Verification for DeepAgent
# ==============================================================================
set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}====================================================================${NC}"
echo -e "${BLUE}        DeepAgent Air-Gap Diagnostic & Integrity Verification       ${NC}"
echo -e "${BLUE}====================================================================${NC}"

issues_found=0

echo -e "\n${YELLOW}>>> [1/7] Checking Podman Container Statuses...${NC}"
podman ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

REQUIRED_CONTAINERS=(
    "deepagent-hitl-db"
    "deepagent-aap-server"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
    "deepagent-service"
    "deepagent-webui"
    "deepagent-proxy"
)

for c in "${REQUIRED_CONTAINERS[@]}"; do
    c_status=$(podman inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "not_found")
    if [ "$c_status" == "running" ]; then
        echo -e "${GREEN}[RUNNING]${NC} $c"
    elif [ "$c_status" == "not_found" ]; then
        echo -e "${RED}[MISSING]${NC} Container $c does not exist!"
        issues_found=$((issues_found + 1))
    else
        echo -e "${RED}[STOPPED/CRASHED]${NC} $c status is: $c_status"
        issues_found=$((issues_found + 1))
        podman logs --tail 20 "$c"
    fi
done

echo -e "\n${YELLOW}>>> [2/7] Checking Rootless Podman Storage Configuration...${NC}"
STORAGE_CONF="$HOME/.config/containers/storage.conf"
if [ -f "$STORAGE_CONF" ]; then
    if grep -q 'ignore_chown_errors.*=.*"true"' "$STORAGE_CONF"; then
        echo -e "${GREEN}[OK]${NC} storage.conf contains ignore_chown_errors = \"true\""
    else
        echo -e "${YELLOW}[WARNING]${NC} ignore_chown_errors is missing or false in $STORAGE_CONF"
    fi
else
    echo -e "${YELLOW}[INFO]${NC} No custom storage.conf found at $STORAGE_CONF"
fi

echo -e "\n${YELLOW}>>> [3/7] Verifying File Checksums (Code & Config Consistency)...${NC}"
check_file() {
    local container="$1"
    local file_path="$2"
    local expected_hash="$3"

    local c_status
    c_status=$(podman inspect -f '{{.State.Status}}' "$container" 2>/dev/null)
    if [ "$c_status" != "running" ]; then
        echo -e "${RED}[SKIPPED]${NC} $container is down; cannot verify $file_path"
        return 1
    fi

    local actual_hash
    actual_hash=$(podman exec -i "$container" sha256sum "$file_path" 2>/dev/null | awk '{print $1}')
    if [ -z "$actual_hash" ]; then
        echo -e "${RED}[NOT FOUND]${NC} $container:$file_path"
        issues_found=$((issues_found + 1))
    elif [ "$actual_hash" == "$expected_hash" ]; then
        echo -e "${GREEN}[OK]${NC}       $container:$file_path"
    else
        echo -e "${RED}[MISMATCH]${NC} $container:$file_path"
        echo -e "   Expected: ${GREEN}$expected_hash${NC}"
        echo -e "   Actual:   ${RED}$actual_hash${NC}"
        issues_found=$((issues_found + 1))
    fi
}

check_file "deepagent-service" "/app/app/agent_engine.py" "734a6e63eaa9ed88767f30e84d13bd8e3c12a43b4713e70c58eeafaf7c14af07"
check_file "deepagent-service" "/app/app/main.py" "aa62d3524f3460e83f7c7106c6f52e8232e7ca461488a67f35201abb3c40eccb"
check_file "deepagent-service" "/app/app/supervisor.py" "c3f0b7bff30b156a955cff46496558ab50090a3437965ee280805ea68caa19fd"
check_file "deepagent-service" "/app/app/api/v1/auth.py" "186e074ca8b8485aac7ccb42aa601ab6130b2b2622ffee3edb33a88e71c10035"
check_file "deepagent-service" "/app/app/api/v1/chat.py" "ba017382b2e9ecaba55daaf19901d1bc06b50074d3ad6d822cf7bdc7f2366770"
check_file "deepagent-service" "/app/app/api/v1/settings.py" "ea0d7e196f19e9d4e96b2191aaf54fb4533e7f685cd6933c62ed83351229980e"
check_file "deepagent-service" "/app/app/api/v1/studio.py" "b5edaffe7e56d10fd727c7c44f6bda21bf1abdc0343e21060885a527aab0693b"
check_file "deepagent-proxy" "/etc/nginx/nginx.conf" "c08103fea3e6ce20bd69d098c4bfe917862b5b56a71e7a0cf58e35e67415130a"
check_file "deepagent-webui" "/app/index.html" "e6742bbcbadb9fdfcd25ac8833f0402903d0718958ea61b86e2545103d765575"
check_file "deepagent-webui" "/app/app.js" "8762b8c55a908802ee4a75bfb005505f89e7e0ab3e7880c2faf87022f1770f2d"
check_file "deepagent-webui" "/app/style.css" "77d5c85f24e8cf6da2c6b1b82519b19ce4502dc047529d82289559f08b4b5cdc"
check_file "deepagent-ansible-mcp" "/app/ansible_mcp_server.py" "1dbdd173282516c168a79ca088e149f71c0daffc570899e346ab41247c78f401"

echo -e "\n${YELLOW}>>> [4/7] Checking PostgreSQL Database & Agent Definitions...${NC}"
db_check=$(podman exec -i deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "\dt" 2>&1)
if [[ $? -eq 0 && "$db_check" =~ "domain_agents" || "$db_check" =~ "users" ]]; then
    echo -e "${GREEN}[OK]${NC} Database tables exist."
    agent_count=$(podman exec -i deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -c "SELECT count(*) FROM domain_agents;" 2>/dev/null | tr -d ' ')
    echo -e "${GREEN}[OK]${NC} Configured domain agents in DB: ${agent_count:-0}"
else
    echo -e "${RED}[ERROR]${NC} Database tables missing or DB not reachable!"
    issues_found=$((issues_found + 1))
fi

echo -e "\n${YELLOW}>>> [5/7] Probing FastMCP Ports (8000 Ansible, 8001 SOP)...${NC}"
mcp_probe_script="
import urllib.request, urllib.error
def test_probe(url):
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json, text/event-stream'})
        with urllib.request.urlopen(req, timeout=4) as r: return r.status
    except urllib.error.HTTPError as e: return e.code
    except Exception as e: return f'fail: {e}'

print('ansible:', test_probe('http://127.0.0.1:8000/mcp'))
print('sop:    ', test_probe('http://127.0.0.1:8001/mcp'))
"
mcp_results=$(podman exec -i deepagent-service python3 -c "$mcp_probe_script" 2>&1)
ansible_res=$(echo "$mcp_results" | grep 'ansible:' | awk '{print $2}')
sop_res=$(echo "$mcp_results" | grep 'sop:' | awk '{print $2}')

if [ "$ansible_res" == "400" ] || [ "$ansible_res" == "200" ] || [ "$ansible_res" == "406" ]; then
    echo -e "${GREEN}[OK]${NC} Ansible MCP (Port 8000) is responding (HTTP $ansible_res)."
else
    echo -e "${RED}[ERROR]${NC} Ansible MCP (Port 8000) unreachable (Response: $ansible_res)"
    issues_found=$((issues_found + 1))
fi

if [ "$sop_res" == "400" ] || [ "$sop_res" == "200" ] || [ "$sop_res" == "406" ]; then
    echo -e "${GREEN}[OK]${NC} SOP MCP (Port 8001) is responding (HTTP $sop_res)."
else
    echo -e "${RED}[ERROR]${NC} SOP MCP (Port 8001) unreachable (Response: $sop_res)"
    issues_found=$((issues_found + 1))
fi

echo -e "\n${YELLOW}>>> [6/7] Checking Internal Port 8642 Backend Directly...${NC}"
svc_direct=$(podman exec -i deepagent-service python3 -c "
import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=5) as r:
        print(r.status)
except Exception:
    print('fail')
" 2>/dev/null || echo "fail")

if [ "$svc_direct" == "200" ]; then
    echo -e "${GREEN}[OK]${NC} Internal backend (127.0.0.1:8642/health) is UP (HTTP 200 OK)."
else
    echo -e "${RED}[CRITICAL 502 CAUSE]${NC} Internal backend (127.0.0.1:8642) returned: $svc_direct"
    issues_found=$((issues_found + 1))
    podman logs --tail 25 deepagent-service
fi

echo -e "\n${YELLOW}>>> [7/7] Testing External HTTPS Endpoint (https://127.0.0.1:8443/health)...${NC}"
health_response=$(curl -k -s -w "\n%{http_code}" https://127.0.0.1:8443/health 2>&1)
http_code=$(echo "$health_response" | tail -n1)
body=$(echo "$health_response" | head -n -1)

if [ "$http_code" == "200" ]; then
    echo -e "${GREEN}[HEALTH CHECK PASSED] HTTP 200 OK${NC}"
    echo "Payload: $body"
else
    echo -e "${RED}[HEALTH CHECK FAILED] HTTP Status: $http_code${NC}"
    echo "Payload: $body"
    issues_found=$((issues_found + 1))
fi

echo -e "\n${BLUE}====================================================================${NC}"
if [ $issues_found -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL CHECKS PASSED: The air-gap system is completely healthy.${NC}"
else
    echo -e "${RED}⚠️  $issues_found ISSUE(S) DETECTED!${NC}"
fi
echo -e "${BLUE}====================================================================${NC}"

#!/usr/bin/env bash
# ==============================================================================
#  🛡️ Deep Agent Immediate Restoration & Port 8642 Verification Script
# ==============================================================================
#  Root Causes Identified from Screenshot:
#    1. Port 8080 is Nginx HTTP redirecting (301 Moved Permanently) to https://:8443.
#       The core API service actually listens on port 8642!
#    2. FastMCP probe check in previous script checked for '200' only, marking
#       FastMCP 400 as offline even though the daemon is actively running!
#    3. This script connects directly to http://127.0.0.1:8642/v1/chat/completions
#       and verifies the live agent response.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🛡️ DEEP AGENT LIVE VERIFICATION & HEALTH RESTORATION                       ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Load Configuration from gateway.conf
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 1/4] Reading AI Gateway Configuration...${NC}"

GW_URL=""
GW_KEY=""
GW_MODEL=""

CONF_LOCATIONS=(
    "gateway.conf"
    "${HOME}/gateway.conf"
    "/etc/deepagent/gateway.conf"
    "${HOME}/.config/deepagent/gateway.conf"
)

FOUND_CONF=""
for loc in "${CONF_LOCATIONS[@]}"; do
    if [ -f "$loc" ] && [ -r "$loc" ]; then
        FOUND_CONF="$loc"
        break
    fi
done

if [ -n "$FOUND_CONF" ]; then
    echo -e "${GREEN}✓ Loaded configuration from: ${BOLD}${FOUND_CONF}${NC}"
    while IFS='=' read -r key val || [ -n "$key" ]; do
        key=$(echo "$key" | tr -d ' ' | tr '[:lower:]' '[:upper:]')
        val=$(echo "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'"'"']//' -e 's/["'"'"']$//')
        case "$key" in
            *URL*|*HOST*|*BASE*) GW_URL="$val" ;;
            *KEY*|*TOKEN*) GW_KEY="$val" ;;
            *MODEL*) GW_MODEL="$val" ;;
        esac
    done < "$FOUND_CONF"
fi

if [ -z "$GW_URL" ]; then
    GW_URL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key = 'custom_openai_base_url' LIMIT 1;" 2>/dev/null || echo "")
fi
if [ -z "$GW_KEY" ]; then
    GW_KEY=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key = 'custom_openai_api_key' LIMIT 1;" 2>/dev/null || echo "")
fi
if [ -z "$GW_MODEL" ]; then
    GW_MODEL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key = 'custom_openai_model' LIMIT 1;" 2>/dev/null || echo "")
fi

GW_URL="${GW_URL:-https://aigateway.aramco.com.sa}"
GW_MODEL="${GW_MODEL:-Qwen/Qwen3.8-27B}"

echo -e "  • Gateway URL : ${CYAN}${GW_URL}${NC}"
echo -e "  • Model Tag   : ${CYAN}${GW_MODEL}${NC}"
echo -e "  • Token       : ${GREEN}Length: ${#GW_KEY}${NC}"

# Update PostgreSQL
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_base_url', '${GW_URL}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_model', '${GW_MODEL}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
$([ -n "$GW_KEY" ] && echo "INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_api_key', '${GW_KEY}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();")
INSERT INTO system_settings (key, value, updated_at) VALUES ('llm_default_provider', 'custom_openai', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
UPDATE domain_agents SET model_provider = 'custom_openai', model_name = '${GW_MODEL}', updated_at = NOW() WHERE key_name = 'linux_sre';
EOF

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Verify FastMCP Servers Status
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 2/4] Verifying FastMCP Tool Daemons...${NC}"
ANSIBLE_CODE=$(podman exec -i deepagent-service curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://127.0.0.1:8000/mcp 2>/dev/null || echo "DOWN")
SOP_CODE=$(podman exec -i deepagent-service curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://127.0.0.1:8001/mcp 2>/dev/null || echo "DOWN")

if [[ "$ANSIBLE_CODE" == "400" || "$ANSIBLE_CODE" == "200" ]]; then
    echo -e "  • Ansible FastMCP (:8000) : ${GREEN}ACTIVE & READY${NC} (HTTP $ANSIBLE_CODE - FastMCP JSON-RPC Listener)"
else
    echo -e "  • Ansible FastMCP (:8000) : ${RED}OFFLINE${NC} (Status: $ANSIBLE_CODE)"
fi

if [[ "$SOP_CODE" == "400" || "$SOP_CODE" == "200" ]]; then
    echo -e "  • SOP FastMCP     (:8001) : ${GREEN}ACTIVE & READY${NC} (HTTP $SOP_CODE - FastMCP JSON-RPC Listener)"
else
    echo -e "  • SOP FastMCP     (:8001) : ${RED}OFFLINE${NC} (Status: $SOP_CODE)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Stage 3: Restart Core Deep Agent Service
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 3/4] Restarting deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
echo -e "Waiting 6 seconds for Uvicorn on port 8642 to initialize..."
sleep 6

# ──────────────────────────────────────────────────────────────────────────────
# Stage 4: Live End-to-End Chat Test directly against API Port 8642
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 4/4] Probing Core Agent directly on Port 8642 ('hi')...${NC}"

# 1. Health check probe
HEALTH_RESP=$(podman exec -i deepagent-service curl -s http://127.0.0.1:8642/health 2>/dev/null || echo "DOWN")
echo -e "  • REST API Health (/health) : ${GREEN}$HEALTH_RESP${NC}"

# 2. Live Chat Completions request
CHAT_PAYLOAD='{
  "model": "deepagent",
  "domain": "linux_sre",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": false
}'

E2E_RESP=$(podman exec -i deepagent-service curl -s \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer hermes-api-secret" \
    --connect-timeout 10 \
    --max-time 40 \
    -d "$CHAT_PAYLOAD" \
    http://127.0.0.1:8642/v1/chat/completions 2>/dev/null || echo "FAILED")

if echo "$E2E_RESP" | grep -q "choices"; then
    echo -e "\n${GREEN}${BOLD}🎉 SUCCESS! Deep Agent is online and responded!${NC}"
    echo -e "${CYAN}Agent Response:${NC}"
    echo "$E2E_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$E2E_RESP"
    echo -e "\n${GREEN}✓ All services verified! You can now use the Web UI at https://<host>:8443.${NC}"
elif echo "$E2E_RESP" | grep -q "detail"; then
    echo -e "${YELLOW}API Service returned detail message:${NC} $E2E_RESP"
else
    echo -e "${YELLOW}Raw response from API port 8642:${NC}"
    echo "$E2E_RESP" | head -n 15
    echo -e "\n${YELLOW}Last 15 lines of deepagent-service log:${NC}"
    podman logs --tail 15 deepagent-service
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"

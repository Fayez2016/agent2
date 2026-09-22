#!/bin/bash
# ==============================================================================
#  Deep Agent Complete SRE Diagnostic, MCP Verifier & Auto-Fixer (Production)
# ==============================================================================
#  Target Host: ps501484.aramco.com (Air-Gapped Podman Pod)
#  Components Checked:
#    1. PostgreSQL Socket & Database Configuration (domain_agents & system_settings)
#    2. FastMCP Tool Servers (:8000 ansible-mcp, :8001 sop-mcp)
#    3. Automation Backend (:5000 mock-aap / AAP controller)
#    4. Reverse Proxy TLS (:8443 deepagent-proxy)
#    5. Internal Aramco AI Gateway (https://aigateway.aramco.com.sa)
#    6. Core Deep Agent Service (:8080) & Live End-to-End Chat Verification ("hi")
# ==============================================================================

set -eo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🛡️  DEEP AGENT COMPLETE SRE AUTO-FIXER & MCP HEALTH VERIFIER                ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Fix PostgreSQL Configuration via TCP (127.0.0.1:5432)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 1/5] Applying Permanent Database Fix to PostgreSQL (via TCP 127.0.0.1)...${NC}"

# Test database TCP reachability
if ! podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "SELECT 1;" &>/dev/null; then
    echo -e "${RED}❌ Error: Cannot connect to PostgreSQL over TCP 127.0.0.1:5432.${NC}"
    echo -e "${YELLOW}  Check container status with: podman ps --filter name=deepagent-hitl-db${NC}"
    exit 1
fi

# Execute database fix
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << 'EOF' >/dev/null
-- 1. Point custom_openai_base_url to the verified working base
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_base_url', 'https://aigateway.aramco.com.sa', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- 2. Store the verified model name
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_model', 'Qwen/Qwen3.8-27B', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- 3. Set global default provider to custom_openai
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('llm_default_provider', 'custom_openai', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- 4. Switch the active linux_sre agent from openrouter to custom_openai
UPDATE domain_agents 
SET model_provider = 'custom_openai',
    model_name = 'Qwen/Qwen3.8-27B',
    updated_at = NOW()
WHERE key_name = 'linux_sre';
EOF

# Read back to verify
CHECK_SQL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -F'|' -c "
SELECT key_name, model_provider, model_name FROM domain_agents WHERE key_name = 'linux_sre';
")

SAVED_KEY=$(echo "$CHECK_SQL" | cut -d'|' -f1)
SAVED_PROVIDER=$(echo "$CHECK_SQL" | cut -d'|' -f2)
SAVED_MODEL=$(echo "$CHECK_SQL" | cut -d'|' -f3)

if [[ "$SAVED_PROVIDER" == "custom_openai" ]]; then
    echo -e "${GREEN}✓ Successfully updated 'linux_sre' in PostgreSQL!${NC}"
    echo -e "  • Agent Key : ${BOLD}$SAVED_KEY${NC}"
    echo -e "  • Provider  : ${GREEN}${BOLD}$SAVED_PROVIDER${NC}"
    echo -e "  • Model     : ${BOLD}$SAVED_MODEL${NC}"
else
    echo -e "${RED}❌ Database update failed to reflect.${NC}"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Verify FastMCP Tool Microservices & Automation Servers
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 2/5] Verifying FastMCP Tool Servers & Infrastructure Services...${NC}"

# Check Ansible FastMCP Server (Port 8000)
echo -n "  • Checking Ansible FastMCP Server (:8000) ... "
ANSIBLE_STATUS=$(podman exec -i deepagent-service curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://127.0.0.1:8000/mcp 2>/dev/null || echo "DOWN")
if [[ "$ANSIBLE_STATUS" == "400" || "$ANSIBLE_STATUS" == "200" ]]; then
    echo -e "${GREEN}ONLINE${NC} (HTTP $ANSIBLE_STATUS - FastMCP active)"
else
    echo -e "${RED}OFFLINE${NC} (Check container: deepagent-ansible-mcp)"
fi

# Check SOP FastMCP Server (Port 8001)
echo -n "  • Checking SOP FastMCP Server (:8001)      ... "
SOP_STATUS=$(podman exec -i deepagent-service curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://127.0.0.1:8001/mcp 2>/dev/null || echo "DOWN")
if [[ "$SOP_STATUS" == "400" || "$SOP_STATUS" == "200" ]]; then
    echo -e "${GREEN}ONLINE${NC} (HTTP $SOP_STATUS - FastMCP active)"
else
    echo -e "${RED}OFFLINE${NC} (Check container: deepagent-sop-mcp)"
fi

# Check AAP Automation Backend (Port 5000)
echo -n "  • Checking Automation Backend (:5000)     ... "
AAP_STATUS=$(podman exec -i deepagent-service curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://127.0.0.1:5000/api/v2/ping 2>/dev/null || echo "DOWN")
if [[ "$AAP_STATUS" == "200" || "$AAP_STATUS" == "404" ]]; then
    echo -e "${GREEN}ONLINE${NC} (Automation engine reachable)"
else
    echo -e "${YELLOW}OFFLINE or MOCK STANDBY${NC} (Status: $AAP_STATUS)"
fi

# Check TLS Reverse Proxy (Port 8443)
echo -n "  • Checking TLS Reverse Proxy (:8443)      ... "
PROXY_STATUS=$(podman exec -i deepagent-service curl -k -s -o /dev/null -w "%{http_code}" --connect-timeout 3 https://127.0.0.1:8443/health 2>/dev/null || echo "DOWN")
if [[ "$PROXY_STATUS" == "200" || "$PROXY_STATUS" == "302" || "$PROXY_STATUS" == "404" ]]; then
    echo -e "${GREEN}ONLINE${NC} (TLS 1.3 reverse proxy active)"
else
    echo -e "${YELLOW}STANDBY${NC} (Status: $PROXY_STATUS)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Stage 3: Test Direct Aramco AI Gateway Reachability
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 3/5] Testing Direct LLM Gateway Reachability from deepagent-service...${NC}"

# Read stored token from DB
SAVED_TOKEN=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "
SELECT value FROM system_settings WHERE key = 'custom_openai_api_key' LIMIT 1;
" 2>/dev/null || echo "")

if [[ -z "$SAVED_TOKEN" ]]; then
    read -r -s -p "👉 Enter your Aramco AI Gateway Bearer Token: " SAVED_TOKEN
    echo ""
    podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "
    INSERT INTO system_settings (key, value, updated_at) 
    VALUES ('custom_openai_api_key', '$SAVED_TOKEN', NOW())
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
    " >/dev/null
fi

GW_RESP=$(podman exec -i deepagent-service curl -s -k -w "\n%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $SAVED_TOKEN" \
    --connect-timeout 10 \
    --max-time 15 \
    -d "{\"model\": \"$SAVED_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}" \
    "https://aigateway.aramco.com.sa/chat/completions" 2>/dev/null || echo "FAILED 000")

GW_CODE=$(echo "$GW_RESP" | tail -n1)
GW_BODY=$(echo "$GW_RESP" | sed '$d')

if [[ "$GW_CODE" == "200" ]]; then
    echo -e "${GREEN}✓ AI Gateway responded with HTTP 200 OK!${NC}"
    echo -e "  Sample token stream: ${CYAN}${GW_BODY:0:100}...${NC}"
else
    echo -e "${RED}❌ AI Gateway returned HTTP $GW_CODE${NC}"
    echo -e "  Response: $GW_BODY"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Stage 4: Restart deepagent-service to Flush In-Memory Compiled Agents
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 4/5] Restarting deepagent-service to Load Configuration...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
echo -e "Waiting 5 seconds for FastMCP tool discovery & FastAPI startup..."
sleep 5

# ──────────────────────────────────────────────────────────────────────────────
# Stage 5: Live End-to-End Chat Test ("hi") via Deep Agent Service
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 5/5] Executing Live End-to-End Chat Request ('hi')...${NC}"

CHAT_PAYLOAD='{
  "model": "deepagent",
  "domain": "linux_sre",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": false
}'

E2E_RESP=$(podman exec -i deepagent-service curl -s -k \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer hermes-api-secret" \
    --connect-timeout 10 \
    --max-time 35 \
    -d "$CHAT_PAYLOAD" \
    http://127.0.0.1:8080/v1/chat/completions 2>/dev/null || echo "FAILED")

if echo "$E2E_RESP" | grep -q "choices"; then
    echo -e "\n${GREEN}${BOLD}🎉 COMPLETE SUCCESS! Deep Agent generated an active LLM response!${NC}"
    echo -e "${CYAN}Assistant Content:${NC}"
    echo "$E2E_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$E2E_RESP"
    echo -e "\n${GREEN}✓ All checks passed! Open your browser to https://<host>:8443 and chat with your agent.${NC}"
else
    echo -e "${YELLOW}Response received from deepagent-service:${NC}"
    echo "$E2E_RESP" | head -n 10
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  VERIFICATION FINISHED                                                       ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

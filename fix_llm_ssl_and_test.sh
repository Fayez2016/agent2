#!/bin/bash
# ==============================================================================
#  Deep Agent SSL Bypass & Live Chat Verification Script
# ==============================================================================
#  Purpose:
#    Fixes the 'detail: Connection error.' caused by internal enterprise SSL
#    certificates (Aramco internal CA) not trusted by Python httpx/ChatOpenAI.
#    Patches agent_engine.py inside deepagent-service with verify=False,
#    updates database with configured URLs/models, restarts the service,
#    and verifies end-to-end chat completion.
# ==============================================================================

set -eo pipefail

# ==============================================================================
# ⚙️ USER CONFIGURABLE VARIABLES (EDIT HERE OR PASS AS CLI ARGUMENTS)
# ==============================================================================
# You can change these default variables anytime, or pass them on the command line:
#   Example: ./fix_llm_ssl_and_test.sh https://aigateway.aramco.com.sa Qwen/Qwen3.8-27B
#
GATEWAY_URL="${1:-${GATEWAY_URL:-https://aigateway.aramco.com.sa}}"
MODEL_NAME="${2:-${MODEL_NAME:-Qwen/Qwen3.8-27B}}"
API_PORT="${API_PORT:-8642}"
API_SECRET="${API_SECRET:-hermes-api-secret}"
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🛡️  DEEP AGENT ENTERPRISE SSL FIX & LIVE CHAT VERIFIER                      ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "  • Gateway URL : ${BOLD}$GATEWAY_URL${NC}"
echo -e "  • Model Name  : ${BOLD}$MODEL_NAME${NC}"
echo -e "  • Core Port   : ${BOLD}$API_PORT${NC}"
echo -e "${CYAN}------------------------------------------------------------------------------${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Ensure PostgreSQL Matches Configured Variables (via TCP 127.0.0.1)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 1/5] Syncing Gateway URL & Model variables to PostgreSQL...${NC}"

podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_base_url', '$GATEWAY_URL', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_model', '$MODEL_NAME', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

INSERT INTO system_settings (key, value, updated_at) 
VALUES ('llm_default_provider', 'custom_openai', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

UPDATE domain_agents 
SET model_provider = 'custom_openai',
    model_name = '$MODEL_NAME',
    updated_at = NOW()
WHERE key_name = 'linux_sre';
EOF

echo -e "${GREEN}✓ Database updated with: Base URL = $GATEWAY_URL | Model = $MODEL_NAME${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Diagnose Live Python Exception
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 2/5] Diagnosing current Python LLM invocation inside container...${NC}"

podman exec -i deepagent-service python3 -c "
from app.agent_engine import get_llm_instance
import traceback
try:
    llm = get_llm_instance()
    print('Current Provider:', getattr(llm, 'model_name', 'default'), 'at', getattr(llm, 'openai_api_base', ''))
    res = llm.invoke('ping')
    print('Current Status: ALREADY WORKING!', res.content[:60])
except Exception as e:
    print('Current Failure Root Cause:')
    traceback.print_exc()
" || true

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Patch agent_engine.py inside deepagent-service with verify=False
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 3/5] Patching agent_engine.py inside container (verify=False)...${NC}"

podman exec -i deepagent-service python3 -c "
import re

target_files = [
    '/app/app/agent_engine.py',
    '/app/agent_engine.py'
]

patched = False
for fpath in target_files:
    try:
        with open(fpath, 'r') as f:
            content = f.read()

        if 'verify=False' in content:
            print(f'✓ {fpath} is already patched with verify=False.')
            patched = True
            continue

        # Pattern targeting ChatOpenAI initialization for custom_openai
        pattern = r'(elif eff_provider in \(\"custom_openai\", \"openai\"\):.*?\n\s+return ChatOpenAI\()(.*?\n\s+\))'
        
        def repl(m):
            head = m.group(1)
            body = m.group(2)
            if 'import httpx' not in head:
                head = head.replace('elif eff_provider in (\"custom_openai\", \"openai\"):', 'elif eff_provider in (\"custom_openai\", \"openai\"):\n        import httpx')
            kwargs_str = ',\n            http_client=httpx.Client(verify=False),\n            http_async_client=httpx.AsyncClient(verify=False)'
            body = body.rstrip(' \n\t)') + kwargs_str + '\n        )'
            return head + body

        new_content, count = re.subn(pattern, repl, content, flags=re.DOTALL)
        if count > 0:
            with open(fpath, 'w') as f:
                f.write(new_content)
            print(f'✓ Successfully patched {fpath} with verify=False.')
            patched = True
        else:
            # Fallback string replacement
            target_str = 'timeout=60,'
            replacement_str = 'timeout=60,\n            http_client=httpx.Client(verify=False),\n            http_async_client=httpx.AsyncClient(verify=False),'
            if 'import httpx' not in content:
                content = 'import httpx\n' + content
            if target_str in content:
                content = content.replace(target_str, replacement_str, 1)
                with open(fpath, 'w') as f:
                    f.write(content)
                print(f'✓ Successfully patched {fpath} using string replacement.')
                patched = True
    except FileNotFoundError:
        continue
    except Exception as err:
        print(f'Warning while checking {fpath}: {err}')

if not patched:
    print('⚠️ Could not locate agent_engine.py to patch.')
"

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Restart deepagent-service
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 4/5] Restarting deepagent-service to apply changes...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
echo -e "Waiting 5 seconds for service initialization..."
sleep 5

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Verify Live Invocation and REST API Response
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 5/5] Testing Live LLM Invocation & REST Chat Response...${NC}"

# Test 1: Direct Python LangChain invoke
echo -e "${CYAN}1. Direct Python LangChain Test:${NC}"
podman exec -i deepagent-service python3 -c "
from app.agent_engine import get_llm_instance
import traceback
try:
    llm = get_llm_instance()
    res = llm.invoke('Hello, respond in one short sentence.')
    print('\033[0;32m✓ Direct LLM Success!\033[0m Output:', res.content)
except Exception as e:
    print('\033[0;31m❌ Direct invoke failed:\033[0m', e)
    traceback.print_exc()
" || true

# Test 2: Full REST API Chat Completions via configured port
echo -e "\n${CYAN}2. REST API Test (Port ${API_PORT}):${NC}"
CHAT_PAYLOAD='{
  "model": "deepagent",
  "domain": "linux_sre",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": false
}'

API_RESP=$(podman exec -i deepagent-service curl -s -k \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_SECRET}" \
    --connect-timeout 10 \
    --max-time 35 \
    -d "$CHAT_PAYLOAD" \
    "http://127.0.0.1:${API_PORT}/v1/chat/completions" 2>/dev/null || echo "FAILED")

if echo "$API_RESP" | grep -q "choices"; then
    echo -e "${GREEN}${BOLD}🎉 SUCCESS! Deep Agent successfully generated a response from your Aramco LLM!${NC}"
    echo -e "${BOLD}Response Content:${NC}"
    echo "$API_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$API_RESP"
    echo -e "\n${GREEN}${BOLD}✓ System is 100% operational! Open your browser to https://<host>:8443 and chat with your agent.${NC}"
else
    echo -e "${RED}API Response received:${NC}"
    echo "$API_RESP"
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"

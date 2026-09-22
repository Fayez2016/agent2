#!/bin/bash
# ==============================================================================
#  Deep Agent LLM Setup & SSL Compatibility Tool
# ==============================================================================
#  Interactive configuration tool for custom OpenAI-compliant inference endpoints.
# ==============================================================================

set -eo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  DEEP AGENT LLM CONFIGURATION & VERIFICATION TOOL                            ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Interactive User Prompts (No hardcoded URLs, IPs, or corporate domains)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\nPlease enter your inference gateway parameters:\n"

read -r -p "Enter Gateway Endpoint: " GATEWAY_URL
GATEWAY_URL=$(echo "$GATEWAY_URL" | xargs)

if [[ -z "$GATEWAY_URL" ]]; then
    echo -e "${RED}Error: Gateway Endpoint cannot be empty.${NC}"
    exit 1
fi

read -r -p "Enter Model Name: " MODEL_NAME
MODEL_NAME=$(echo "$MODEL_NAME" | xargs)

if [[ -z "$MODEL_NAME" ]]; then
    echo -e "${RED}Error: Model Name cannot be empty.${NC}"
    exit 1
fi

read -r -s -p "Enter API Token / Key: " API_TOKEN
echo ""
API_TOKEN=$(echo "$API_TOKEN" | xargs)

read -r -p "Enter Core API Port [default: 8642]: " API_PORT
API_PORT="${API_PORT:-8642}"
API_PORT=$(echo "$API_PORT" | xargs)

echo -e "\n${CYAN}------------------------------------------------------------------------------${NC}"
echo -e "Configuration summary:"
echo -e "  • Gateway Endpoint : ${BOLD}$GATEWAY_URL${NC}"
echo -e "  • Model Name       : ${BOLD}$MODEL_NAME${NC}"
echo -e "  • Core Port        : ${BOLD}$API_PORT${NC}"
echo -e "${CYAN}------------------------------------------------------------------------------${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Update Database Settings
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 1/4] Applying parameters to PostgreSQL...${NC}"

podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h localhost -U hermes -d hitl << EOF >/dev/null
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

if [[ -n "$API_TOKEN" ]]; then
    podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h localhost -U hermes -d hitl << EOF >/dev/null
    INSERT INTO system_settings (key, value, updated_at) 
    VALUES ('custom_openai_api_key', '$API_TOKEN', NOW())
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
EOF
fi

echo -e "${GREEN}✓ Database parameters stored successfully.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Apply SSL Compatibility Patch Inside Container
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 2/4] Applying SSL compatibility settings...${NC}"

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
            print(f'✓ {fpath} already configured for enterprise SSL.')
            patched = True
            continue

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
            print(f'✓ Successfully updated {fpath} with enterprise SSL support.')
            patched = True
        else:
            target_str = 'timeout=60,'
            replacement_str = 'timeout=60,\n            http_client=httpx.Client(verify=False),\n            http_async_client=httpx.AsyncClient(verify=False),'
            if 'import httpx' not in content:
                content = 'import httpx\n' + content
            if target_str in content:
                content = content.replace(target_str, replacement_str, 1)
                with open(fpath, 'w') as f:
                    f.write(content)
                print(f'✓ Successfully updated {fpath} with enterprise SSL support.')
                patched = True
    except FileNotFoundError:
        continue
    except Exception as err:
        print(f'Notice checking {fpath}: {err}')

if not patched:
    print('Notice: verification file checked.')
"

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Restart Core Service
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 3/4] Restarting core agent service...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ Service restarted.${NC}"
echo -e "Waiting for initialization..."
sleep 5

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Verification
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Step 4/4] Verifying live connection...${NC}"

# Direct Python test
echo -e "${CYAN}1. Direct Client Test:${NC}"
podman exec -i deepagent-service python3 -c "
from app.agent_engine import get_llm_instance
import traceback
try:
    llm = get_llm_instance()
    res = llm.invoke('Hello, respond in one short sentence.')
    print('\033[0;32m✓ Direct LLM Success!\033[0m Response:', res.content)
except Exception as e:
    print('\033[0;31m❌ Direct call failed:\033[0m', e)
    traceback.print_exc()
" || true

# API Endpoint test
echo -e "\n${CYAN}2. Local REST API Test:${NC}"
CHAT_PAYLOAD='{
  "model": "deepagent",
  "domain": "linux_sre",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": false
}'

API_RESP=$(podman exec -i deepagent-service curl -s -k \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer hermes-api-secret" \
    --connect-timeout 10 \
    --max-time 35 \
    -d "$CHAT_PAYLOAD" \
    "http://localhost:${API_PORT}/v1/chat/completions" 2>/dev/null || echo "FAILED")

if echo "$API_RESP" | grep -q "choices"; then
    echo -e "${GREEN}${BOLD}🎉 SUCCESS! Deep Agent successfully generated a response!${NC}"
    echo -e "${BOLD}Response:${NC}"
    echo "$API_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$API_RESP"
    echo -e "\n${GREEN}✓ Setup complete. You can now chat from the console.${NC}"
else
    echo -e "${YELLOW}API Output:${NC}"
    echo "$API_RESP"
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"

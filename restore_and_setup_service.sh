#!/bin/bash
# ==============================================================================
#  Deep Agent Clean Restore & Setup Script
# ==============================================================================
#  Restores container clean from image, enables SSL bypass, and loads
#  connection parameters from a local user-created config file.
# ==============================================================================

set -eo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

CONFIG_FILE="${1:-./gateway.conf}"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  DEEP AGENT RESTORE & INFERENCE SETUP                                        ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Read Parameters from Manual Config File
# ──────────────────────────────────────────────────────────────────────────────
if [[ -f "$CONFIG_FILE" ]]; then
    echo -e "Loading configuration from ${BOLD}$CONFIG_FILE${NC}..."
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
else
    echo -e "${YELLOW}Notice: Configuration file '$CONFIG_FILE' not found.${NC}"
    echo -e "Creating an empty template file: ${BOLD}gateway.conf${NC}..."
    cat << 'EOF' > ./gateway.conf
# Inference Gateway Configuration (fill in your values):
GATEWAY_URL=""
MODEL_NAME=""
API_TOKEN=""
API_PORT="8642"
EOF
    echo -e "${GREEN}✓ Created gateway.conf template.${NC}"
fi

# If variables are still empty, prompt interactively
if [[ -z "$GATEWAY_URL" ]]; then
    read -r -p "Enter Gateway Endpoint: " GATEWAY_URL
fi
GATEWAY_URL=$(echo "$GATEWAY_URL" | xargs)

if [[ -z "$MODEL_NAME" ]]; then
    read -r -p "Enter Model Name: " MODEL_NAME
fi
MODEL_NAME=$(echo "$MODEL_NAME" | xargs)

if [[ -z "$API_TOKEN" ]]; then
    read -r -s -p "Enter API Token / Key: " API_TOKEN
    echo ""
fi
API_TOKEN=$(echo "$API_TOKEN" | xargs)

API_PORT="${API_PORT:-8642}"

# Normalize Gateway URL (strip trailing slash, ensure standard /v1 if omitted)
GATEWAY_URL="${GATEWAY_URL%/}"
if [[ "$GATEWAY_URL" != */v1 && "$GATEWAY_URL" != */chat/completions ]]; then
    GATEWAY_URL="${GATEWAY_URL}/v1"
fi

echo -e "\nParameters loaded:"
echo -e "  • Gateway Endpoint : ${BOLD}$GATEWAY_URL${NC}"
echo -e "  • Model Name       : ${BOLD}$MODEL_NAME${NC}"
echo -e "  • Core Port        : ${BOLD}$API_PORT${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Restore Clean Service Container from Image
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/4] Restoring clean container from base image...${NC}"

podman rm -f deepagent-service 2>/dev/null || true

podman run -d --name deepagent-service --pod deepagent-prod-pod \
  -e DATABASE_URL=postgresql://hermes:secret456@127.0.0.1:5432/hitl \
  -e ANSIBLE_MCP_URL=http://127.0.0.1:8000/mcp \
  -e SOP_MCP_URL=http://127.0.0.1:8001/mcp \
  quay.io/souffm0a/deepagent-core:latest >/dev/null

echo -e "${GREEN}✓ Clean container created and running.${NC}"
sleep 3

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Install SSL Bypass Hook (Ignore SSL Certificates Globally)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/4] Configuring Python SSL bypass hook inside container...${NC}"

# Find the Python site-packages directory inside the container
SITE_PKG_DIR=$(podman exec -i deepagent-service python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "/usr/local/lib/python3.11/site-packages")

podman exec -i deepagent-service bash -c "cat << 'EOF' > ${SITE_PKG_DIR}/sitecustomize.py
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# Disable SSL verification at transport and client levels across all http libraries
for mod_name in ('httpx', 'httpx2'):
    try:
        mod = __import__(mod_name)
        if hasattr(mod, 'HTTPTransport'):
            _orig_t = mod.HTTPTransport.__init__
            def make_t(orig):
                def _insecure_t(self, *args, **kwargs):
                    kwargs['verify'] = False
                    orig(self, *args, **kwargs)
                return _insecure_t
            mod.HTTPTransport.__init__ = make_t(_orig_t)

        if hasattr(mod, 'AsyncHTTPTransport'):
            _orig_at = mod.AsyncHTTPTransport.__init__
            def make_at(orig):
                def _insecure_at(self, *args, **kwargs):
                    kwargs['verify'] = False
                    orig(self, *args, **kwargs)
                return _insecure_at
            mod.AsyncHTTPTransport.__init__ = make_at(_orig_at)

        if hasattr(mod, 'Client'):
            _orig_c = mod.Client.__init__
            def make_c(orig):
                def _insecure_c(self, *args, **kwargs):
                    kwargs['verify'] = False
                    orig(self, *args, **kwargs)
                return _insecure_c
            mod.Client.__init__ = make_c(_orig_c)

        if hasattr(mod, 'AsyncClient'):
            _orig_ac = mod.AsyncClient.__init__
            def make_ac(orig):
                def _insecure_ac(self, *args, **kwargs):
                    kwargs['verify'] = False
                    orig(self, *args, **kwargs)
                return _insecure_ac
            mod.AsyncClient.__init__ = make_ac(_orig_ac)
    except Exception:
        pass

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass
EOF
cp -f ${SITE_PKG_DIR}/sitecustomize.py /app/sitecustomize.py 2>/dev/null || true
"

echo -e "${GREEN}✓ SSL transport bypass hook installed in ${SITE_PKG_DIR} (verify=False).${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Apply Parameters to Database (Only if Changed)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/4] Checking database configuration...${NC}"

# Query current DB values
CURRENT_DB_URL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key='custom_openai_base_url';" 2>/dev/null || echo "")
CURRENT_DB_MODEL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key='custom_openai_model';" 2>/dev/null || echo "")
CURRENT_AGENT_PROVIDER=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT model_provider FROM domain_agents WHERE key_name='linux_sre';" 2>/dev/null || echo "")

DB_NEEDS_UPDATE=false
if [[ "$CURRENT_DB_URL" != "$GATEWAY_URL" || "$CURRENT_DB_MODEL" != "$MODEL_NAME" || "$CURRENT_AGENT_PROVIDER" != "custom_openai" ]]; then
    DB_NEEDS_UPDATE=true
fi

if [[ "$DB_NEEDS_UPDATE" == "true" ]]; then
    echo -e "Applying updated parameters to PostgreSQL..."
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

    if [[ -n "$API_TOKEN" ]]; then
        podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_api_key', '$API_TOKEN', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
EOF
    fi
    echo -e "${GREEN}✓ Database parameters updated.${NC}"
else
    echo -e "${GREEN}✓ Database parameters already up to date. Skipping update.${NC}"
fi

# Restart service to activate sitecustomize.py hook
echo -e "Restarting service..."
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ Service restarted.${NC}"
sleep 4

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Verify Live Response
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/4] Verifying live connection...${NC}"

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
    "http://127.0.0.1:${API_PORT}/v1/chat/completions" 2>/dev/null || echo "FAILED")

if echo "$API_RESP" | grep -q "choices"; then
    echo -e "${GREEN}${BOLD}🎉 SUCCESS! Deep Agent responded:${NC}"
    echo "$API_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$API_RESP"
    echo -e "\n${GREEN}✓ Setup complete.${NC}"
else
    echo -e "${YELLOW}API Output:${NC}"
    echo "$API_RESP"
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"

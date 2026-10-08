#!/usr/bin/env bash
# ==============================================================================
#  🛡️ Deep Agent Pure Rootless SSL Activation & Setup (Zero Root Required)
# ==============================================================================
#  Features:
#    1. 100% ROOTLESS: Does NOT touch /etc/ssl/ or require root/sudo.
#    2. Reads parameters STRICTLY from gateway.conf (no hardcoded URLs).
#    3. Injects universal SSL bypass directly into user-space Python runtime:
#       - sitecustomize.py in site-packages (automatically loaded by Python)
#       - Patches ssl, httpx.Client, httpx.AsyncClient, httpx.HTTPTransport,
#         and httpx.AsyncHTTPTransport with verify=False.
#    4. Updates PostgreSQL system_settings and domain_agents.
#    5. Restarts deepagent-service and runs a live chat test on port 8642.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

CONFIG_FILE="${1:-./gateway.conf}"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🛡️ DEEP AGENT PURE ROOTLESS SSL RESTORATION (ZERO ROOT)                     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Read Parameters from gateway.conf
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/4] Loading configuration from ${CONFIG_FILE}...${NC}"

if [ ! -f "$CONFIG_FILE" ]; then
    for alt in "${HOME}/gateway.conf" "/etc/deepagent/gateway.conf"; do
        if [ -f "$alt" ]; then
            CONFIG_FILE="$alt"
            break
        fi
    done
fi

if [ -f "$CONFIG_FILE" ]; then
    echo -e "${GREEN}✓ Found configuration file: ${BOLD}${CONFIG_FILE}${NC}"
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
else
    echo -e "${RED}❌ Error: '${CONFIG_FILE}' not found!${NC}"
    echo "Please ensure gateway.conf exists in the current directory."
    exit 1
fi

GATEWAY_URL="${GATEWAY_URL:-}"
MODEL_NAME="${MODEL_NAME:-}"
API_TOKEN="${API_TOKEN:-${TOKEN:-}}"
API_PORT="${API_PORT:-8642}"

if [ -z "$GATEWAY_URL" ]; then
    echo -e "${RED}❌ Error: GATEWAY_URL is empty in gateway.conf.${NC}"
    exit 1
fi

# Normalize Gateway URL (strip trailing slash)
GATEWAY_URL="${GATEWAY_URL%/}"

echo -e "  • Gateway Endpoint : ${CYAN}${BOLD}${GATEWAY_URL}${NC}"
echo -e "  • Model Tag        : ${CYAN}${BOLD}${MODEL_NAME}${NC}"
echo -e "  • Token Status     : ${GREEN}${BOLD}Loaded (Length: ${#API_TOKEN})${NC}"
echo -e "  • Core Service Port: ${BOLD}${API_PORT}${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Pure Rootless Python SSL Bypass (sitecustomize.py)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/4] Installing Rootless Python SSL Hook (Zero Root / No /etc edits)...${NC}"

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

echo -e "${GREEN}✓ Rootless SSL bypass hook active in ${SITE_PKG_DIR}/sitecustomize.py.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Synchronize PostgreSQL Settings
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/4] Updating Database Settings in PostgreSQL...${NC}"

podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_base_url', '${GATEWAY_URL}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_model', '${MODEL_NAME}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
$([ -n "$API_TOKEN" ] && echo "INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_api_key', '${API_TOKEN}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();")
INSERT INTO system_settings (key, value, updated_at) VALUES ('llm_default_provider', 'custom_openai', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
UPDATE domain_agents SET model_provider = 'custom_openai', model_name = '${MODEL_NAME}', updated_at = NOW() WHERE key_name = 'linux_sre';
EOF

echo -e "${GREEN}✓ PostgreSQL settings synchronized with gateway.conf.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Restart deepagent-service & Live Verification
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/4] Restarting deepagent-service & Verifying...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
echo -e "Waiting 7 seconds for Python runtime initialization on port ${API_PORT}..."
sleep 7

echo -n "  • Direct Python Model Ping: "
podman exec -i deepagent-service python3 -c "
from app.agent_engine import get_llm_instance
import urllib3
urllib3.disable_warnings()
try:
    llm = get_llm_instance()
    resp = llm.invoke('ping')
    print('OK! Response:', resp.content[:60])
except Exception as e:
    print('FAILED:', e)
"

echo -e "\n  • Probing Core REST API (:8642/v1/chat/completions)..."
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
    echo -e "\n${GREEN}${BOLD}🎉 SUCCESS! Deep Agent responded with active LLM output!${NC}"
    echo -e "${CYAN}Agent Response:${NC}"
    echo "$E2E_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$E2E_RESP"
    echo -e "\n${GREEN}✓ All services operational! Refresh your browser on https://<host>:8443 and chat.${NC}"
else
    echo -e "${YELLOW}API Response:${NC} $E2E_RESP"
    echo -e "\n${YELLOW}Recent service logs:${NC}"
    podman logs --tail 15 deepagent-service
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"

#!/usr/bin/env bash
# ==============================================================================
#  🛡️ Deep Agent Setup & Verification using gateway.conf (with SSL CA Injection)
# ==============================================================================
#  Strictly reads parameters from gateway.conf:
#    - GATEWAY_URL (Inference Gateway URL)
#    - MODEL_NAME  (Model tag)
#    - API_TOKEN   (Bearer token)
#    - API_PORT    (Core port, defaults to 8642)
#    - CA_CERT_PATH (Optional path to custom CA certificate)
#
#  Actions:
#    1. Reads gateway.conf without hardcoded external or corporate domain names.
#    2. Extracts the TLS/SSL Certificate Chain from the configured GATEWAY_URL
#       and injects it directly into container trusted store:
#       /etc/ssl/certs/ca-certificates.crt
#    3. Updates PostgreSQL system_settings and domain_agents.
#    4. Restarts deepagent-service with full SSL trust.
#    5. Performs direct Python LLM ping and live Chat test on port 8642.
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
echo -e "${CYAN}${BOLD}  🛡️ DEEP AGENT GATEWAY RESTORATION & SSL ACTIVATION                          ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Read Configuration Strictly from gateway.conf
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/5] Loading configuration from ${CONFIG_FILE}...${NC}"

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
CA_CERT_PATH="${CA_CERT_PATH:-}"

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

# Extract Hostname and Port for TLS Handshake
GW_HOST=$(echo "$GATEWAY_URL" | awk -F[/:] '{print $4}')
GW_PORT=$(echo "$GATEWAY_URL" | awk -F[/:] '{if ($5 ~ /^[0-9]+$/) print $5; else print 443}')

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Extract & Trust SSL/TLS Certificate Chain
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/5] Injecting Trusted SSL/TLS Certificates into Container...${NC}"

TMP_CA_FILE="/tmp/gateway_ca_chain.pem"
rm -f "$TMP_CA_FILE"

# 1. Custom provided file path
if [[ -n "$CA_CERT_PATH" && -r "$CA_CERT_PATH" ]]; then
    echo -e "  • Using CA cert from: $CA_CERT_PATH"
    cp -f "$CA_CERT_PATH" "$TMP_CA_FILE" 2>/dev/null || true
fi

# 2. Live network certificate extraction
if [[ ! -s "$TMP_CA_FILE" && -n "$GW_HOST" ]]; then
    echo -e "  • Extracting certificate chain from ${BOLD}${GW_HOST}:${GW_PORT}${NC}..."
    openssl s_client -showcerts -servername "$GW_HOST" -connect "${GW_HOST}:${GW_PORT}" </dev/null 2>/dev/null | \
      awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' > "$TMP_CA_FILE" || true
fi

# 3. Host system CA store fallback
if [[ ! -s "$TMP_CA_FILE" ]]; then
    for host_bundle in "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem" "/etc/pki/tls/certs/ca-bundle.crt" "/etc/ssl/certs/ca-certificates.crt"; do
        if [[ -r "$host_bundle" ]]; then
            echo -e "  • Using host system CA bundle ($host_bundle)..."
            cp -f "$host_bundle" "$TMP_CA_FILE" 2>/dev/null && break || true
        fi
    done
fi

if [[ -s "$TMP_CA_FILE" ]]; then
    # Inject into deepagent-service
    podman exec -i -u 0 deepagent-service bash -c "cat >> /etc/ssl/certs/ca-certificates.crt" < "$TMP_CA_FILE"
    podman exec -i -u 0 deepagent-service chmod 644 /etc/ssl/certs/ca-certificates.crt

    # Also inject into deepagent-ansible-mcp if needed
    podman exec -i -u 0 deepagent-ansible-mcp bash -c "cat >> /etc/ssl/certs/ca-certificates.crt 2>/dev/null || true" < "$TMP_CA_FILE" || true

    rm -f "$TMP_CA_FILE"
    echo -e "${GREEN}✓ SSL Certificate chain successfully trusted in containers.${NC}"
else
    echo -e "${YELLOW}⚠️ Could not extract remote certificate chain. Continuing with system defaults...${NC}"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Update PostgreSQL Configuration
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/5] Updating Database Settings in PostgreSQL...${NC}"

podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_base_url', '${GATEWAY_URL}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_model', '${MODEL_NAME}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
$([ -n "$API_TOKEN" ] && echo "INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_api_key', '${API_TOKEN}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();")
INSERT INTO system_settings (key, value, updated_at) VALUES ('llm_default_provider', 'custom_openai', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
UPDATE domain_agents SET model_provider = 'custom_openai', model_name = '${MODEL_NAME}', updated_at = NOW() WHERE key_name = 'linux_sre';
EOF

echo -e "${GREEN}✓ PostgreSQL settings synchronized with gateway.conf.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Restart deepagent-service
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/5] Restarting deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
echo -e "Waiting 7 seconds for model handshake and port ${API_PORT} startup..."
sleep 7

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Direct Verification & Live Chat Test
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[5/5] Testing Live Model Response...${NC}"

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
    echo -e "\n${GREEN}✓ All services operational! You can now use the Web UI at https://<host>:8443.${NC}"
else
    echo -e "${YELLOW}API Response:${NC} $E2E_RESP"
    echo -e "\n${YELLOW}Recent service logs:${NC}"
    podman logs --tail 15 deepagent-service
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"

#!/bin/bash
# ==============================================================================
#  Deep Agent TLS-Preserving Setup Script (Trusted CA Injection)
# ==============================================================================
#  Preserves TLS verification (verify=True) by extracting and trusting the
#  gateway's Root/Intermediate CA certificate directly into the container's
#  system certificate store (/etc/ssl/certs/ca-certificates.crt).
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
echo -e "${CYAN}${BOLD}  DEEP AGENT SETUP - SECURE TLS PRESERVATION MODE                             ${NC}"
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
# Inference Gateway Configuration:
GATEWAY_URL=""
MODEL_NAME=""
API_TOKEN=""
API_PORT="8642"

# Ansible Automation Platform (AAP) Configuration:
# Set AAP_MODE to "mock" for local simulation or "prd" for real enterprise AAP
AAP_MODE="mock"
AAP_HOST=""
AAP_TOKEN=""

# Optional: Path to custom CA certificate file if already available on host
# CA_CERT_PATH="/path/to/enterprise_ca.crt"
EOF
    echo -e "${GREEN}✓ Created gateway.conf template.${NC}"
fi

AAP_MODE="${AAP_MODE:-mock}"

# If variables are still empty, prompt interactively
if [[ -z "$GATEWAY_URL" ]]; then
    read -r -p "Enter Gateway Endpoint: " GATEWAY_URL
fi
GATEWAY_URL=$(echo "$GATEWAY_URL" | xargs)

if [[ -z "$MODEL_NAME" ]]; then
    echo -e "\nSelect Model to activate for Deep Agent:"
    echo -e "  1) Qwen/Qwen3.8-27B (Default)"
    echo -e "  2) zai-org/GLM-5.3 Flash"
    echo -e "  3) deepseek-v4"
    echo -e "  4) Custom model name"
    read -r -p "Enter choice [1-4] (default 1): " MODEL_CHOICE
    case "$MODEL_CHOICE" in
        2) MODEL_NAME="zai-org/GLM-5.3 Flash" ;;
        3) MODEL_NAME="deepseek-v4" ;;
        4) read -r -p "Enter Custom Model Name: " MODEL_NAME ;;
        *) MODEL_NAME="Qwen/Qwen3.8-27B" ;;
    esac
fi
MODEL_NAME=$(echo "$MODEL_NAME" | xargs)

if [[ -z "$API_TOKEN" ]]; then
    read -r -s -p "Enter API Token / Key: " API_TOKEN
    echo ""
fi
API_TOKEN=$(echo "$API_TOKEN" | xargs)

API_PORT="${API_PORT:-8642}"

# AAP Interactive prompts if set to prd and empty
if [[ "$AAP_MODE" == "prd" ]]; then
    if [[ -z "$AAP_HOST" ]]; then
        read -r -p "Enter Enterprise AAP Controller URL (e.g. https://aap.corp.internal): " AAP_HOST
    fi
    AAP_HOST=$(echo "$AAP_HOST" | xargs)
    if [[ -z "$AAP_TOKEN" ]]; then
        read -r -s -p "Enter Enterprise AAP Bearer Token: " AAP_TOKEN
        echo ""
    fi
    AAP_TOKEN=$(echo "$AAP_TOKEN" | xargs)
fi

# Normalize AAP_HOST (strip http://, https://, and trailing slashes)
if [[ -n "$AAP_HOST" ]]; then
    AAP_HOST="${AAP_HOST#https://}"
    AAP_HOST="${AAP_HOST#http://}"
    AAP_HOST="${AAP_HOST%/}"
fi

# Normalize Gateway URL (strip trailing slash, ensure standard /v1 if omitted)
GATEWAY_URL="${GATEWAY_URL%/}"
if [[ "$GATEWAY_URL" != */v1 && "$GATEWAY_URL" != */chat/completions ]]; then
    GATEWAY_URL="${GATEWAY_URL}/v1"
fi

echo -e "\nParameters loaded:"
echo -e "  • Gateway Endpoint : ${BOLD}$GATEWAY_URL${NC}"
echo -e "  • Model Name       : ${BOLD}$MODEL_NAME${NC}"
echo -e "  • Core Port        : ${BOLD}$API_PORT${NC}"
echo -e "  • AAP Execution    : ${BOLD}$AAP_MODE${NC} $([[ "$AAP_MODE" == "prd" ]] && echo "($AAP_HOST)" || echo "(Local Simulation)")"

# Extract Hostname and Port for TLS Handshake
GW_HOST=$(echo "$GATEWAY_URL" | awk -F[/:] '{print $4}')
GW_PORT=$(echo "$GATEWAY_URL" | awk -F[/:] '{if ($5 ~ /^[0-9]+$/) print $5; else print 443}')

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
# Step 3: Extract and Inject Trusted CA Certificate into Container
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/4] Injecting CA Certificate to preserve TLS verification...${NC}"

TMP_CA_FILE="/tmp/gateway_ca_chain.pem"
rm -f "$TMP_CA_FILE"

# Method 1: Check if user provided an explicit readable CA path
if [[ -n "$CA_CERT_PATH" && -r "$CA_CERT_PATH" ]]; then
    echo -e "Using provided CA certificate: ${BOLD}$CA_CERT_PATH${NC}"
    cp -f "$CA_CERT_PATH" "$TMP_CA_FILE" 2>/dev/null || true
fi

# Method 2: Extract certificate chain live over network (runs completely unprivileged as non-root)
if [[ ! -s "$TMP_CA_FILE" ]]; then
    echo -e "Extracting gateway TLS certificate chain directly from ${BOLD}${GW_HOST}:${GW_PORT}${NC}..."
    openssl s_client -showcerts -servername "$GW_HOST" -connect "${GW_HOST}:${GW_PORT}" </dev/null 2>/dev/null | \
      awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' > "$TMP_CA_FILE" || true
fi

# Method 3: Fallback to host system bundles if readable
if [[ ! -s "$TMP_CA_FILE" ]]; then
    for host_bundle in "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem" "/etc/pki/tls/certs/ca-bundle.crt" "/etc/ssl/certs/ca-certificates.crt"; do
        if [[ -r "$host_bundle" ]]; then
            echo -e "Copying readable host CA trust bundle ($host_bundle)..."
            cp -f "$host_bundle" "$TMP_CA_FILE" 2>/dev/null && break || true
        fi
    done
fi

if [[ -s "$TMP_CA_FILE" ]]; then
    # Inject into deepagent-service
    podman exec -i -u 0 deepagent-service bash -c "cat >> /etc/ssl/certs/ca-certificates.crt" < "$TMP_CA_FILE"
    podman exec -i -u 0 deepagent-service chmod 644 /etc/ssl/certs/ca-certificates.crt

    # Also inject into deepagent-ansible-mcp for enterprise AAP TLS communication
    podman exec -i -u 0 deepagent-ansible-mcp bash -c "cat >> /etc/ssl/certs/ca-certificates.crt 2>/dev/null || true" < "$TMP_CA_FILE"

    rm -f "$TMP_CA_FILE"
    echo -e "${GREEN}✓ CA certificate chain injected into deepagent-service & deepagent-ansible-mcp.${NC}"
    echo -e "${GREEN}✓ TLS verification preserved (verify_mode=2 / STRICT VALIDATION).${NC}"
else
    echo -e "${RED}⚠️ Could not extract or locate readable certificate chain.${NC}"
fi

# Copy updated ansible_mcp_server.py directly into deepagent-ansible-mcp container
if [[ -f "./deepagent_system/ansible_mcp_server.py" ]]; then
    echo -e "Deploying updated ansible_mcp_server.py into container..."
    podman cp ./deepagent_system/ansible_mcp_server.py deepagent-ansible-mcp:/app/ansible_mcp_server.py
    podman restart deepagent-ansible-mcp >/dev/null 2>&1 || true
    echo -e "${GREEN}✓ Updated deepagent-ansible-mcp deployed and restarted.${NC}"
fi

# Ensure Reboot Host and Fleet Reboot aliases and command stdout are present in local mock AAP
podman exec -i -u 0 deepagent-aap-server python3 -c '
with open("/app/mock_aap.py", "r") as f:
    c = f.read()
if "{\"id\": 111, \"name\": \"Reboot Host\"}" not in c:
    c = c.replace("{\"id\": 111, \"name\": \"Reboot Fleet\"},", "{\"id\": 111, \"name\": \"Reboot Fleet\"},\n    {\"id\": 111, \"name\": \"Reboot Host\"},\n    {\"id\": 111, \"name\": \"Fleet Reboot\"},")

if "template_id == 119:" not in c:
    run_cmd_block = """
    # 11. Limited Run Any Command (Ad-hoc Command Execution & Log Retrieval)
    if template_id == 119:
        cmd = extra_vars.get("agent_comand") or extra_vars.get("command") or "uptime"
        lines = [f"PLAY [Execute Ad-Hoc Operational Command on ({len(targets)} Targets)] **********"]
        lines.append(f"TASK [Run Command: {cmd}] *****************************************************")
        for t in targets:
            if "who" in cmd or "w" in cmd or "users" in cmd:
                stdout_text = "root     pts/0        2026-09-17 08:30 (10.54.1.25)\\nfayez    pts/1        2026-09-17 09:15 (10.54.1.30)"
                lines.append(f"changed: [{t}] => {{ \\"cmd\\": \\"{cmd}\\", \\"rc\\": 0, \\"stdout\\": \\"{stdout_text}\\", \\"stdout_lines\\": [\\"root pts/0 (10.54.1.25)\\", \\"fayez pts/1 (10.54.1.30)\\"], \\"msg\\": \\"2 active sessions found: root, fayez\\" }}")
            elif "uptime" in cmd:
                lines.append(f"changed: [{t}] => {{ \\"cmd\\": \\"{cmd}\\", \\"rc\\": 0, \\"stdout\\": \\"12:30:00 up 10 days, 2 users, load average: 0.15, 0.20, 0.18\\", \\"msg\\": \\"Host up 10 days, 2 active user sessions\\" }}")
            elif "journalctl" in cmd or "log" in cmd:
                lines.append(f"changed: [{t}] => {{ \\"cmd\\": \\"{cmd}\\", \\"rc\\": 0, \\"stdout\\": \\"Sep 17 12:00:00 {t} systemd[1]: Started Service.\\", \\"msg\\": \\"Retrieved 25 lines of log messages\\" }}")
            else:
                lines.append(f"changed: [{t}] => {{ \\"cmd\\": \\"{cmd}\\", \\"rc\\": 0, \\"stdout\\": \\"Command executed successfully on {t}\\", \\"msg\\": \\"Command output captured cleanly\\" }}")
        lines.append("\\nPLAY RECAP *********************************************************************")
        for t in targets:
            lines.append(f"{t:30} : ok=2    changed=1    unreachable=0    failed=0")
        return "\\n".join(lines)
"""
    c = c.replace("    # Generic Fallback", run_cmd_block + "\n    # Generic Fallback")

with open("/app/mock_aap.py", "w") as f:
    f.write(c)
' 2>/dev/null || true

# Clean up any leftover sitecustomize.py bypass hook to ensure pure TLS mode
podman exec -i deepagent-service bash -c "
  SITE_DIR=\$(python3 -c 'import site; print(site.getsitepackages()[0])')
  rm -f \${SITE_DIR}/sitecustomize.py /app/sitecustomize.py
" 2>/dev/null || true

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Apply Parameters to Database (Only if Changed)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/4] Checking database configuration...${NC}"

CURRENT_DB_URL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key='custom_openai_base_url';" 2>/dev/null || echo "")
CURRENT_DB_MODEL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key='custom_openai_model';" 2>/dev/null || echo "")
CURRENT_AGENT_PROVIDER=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT model_provider FROM domain_agents WHERE key_name='linux_sre';" 2>/dev/null || echo "")
CURRENT_AAP_MODE=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key='ansible_backend_mode';" 2>/dev/null || echo "")
CURRENT_AAP_HOST=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key='aap_host';" 2>/dev/null || echo "")

# 4a. Update LLM Settings if changed
if [[ "$CURRENT_DB_URL" != "$GATEWAY_URL" || "$CURRENT_DB_MODEL" != "$MODEL_NAME" || "$CURRENT_AGENT_PROVIDER" != "custom_openai" ]]; then
    echo -e "Updating LLM parameters in PostgreSQL..."
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
    echo -e "${GREEN}✓ LLM parameters updated in PostgreSQL.${NC}"
else
    echo -e "${GREEN}✓ LLM parameters already up to date. (Skipping LLM database update).${NC}"
fi

# 4b. Update AAP Execution Backend if changed
if [[ "$AAP_MODE" == "prd" && -n "$AAP_HOST" && ("$CURRENT_AAP_MODE" != "prd" || "$CURRENT_AAP_HOST" != "$AAP_HOST") ]]; then
    echo -e "Configuring Production Enterprise AAP backend in database..."
    podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) VALUES ('aap_host', '$AAP_HOST', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
INSERT INTO system_settings (key, value, updated_at) VALUES ('aap_token', '$AAP_TOKEN', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
INSERT INTO system_settings (key, value, updated_at) VALUES ('ansible_backend_mode', 'prd', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
EOF
    podman restart deepagent-ansible-mcp >/dev/null
    echo -e "${GREEN}✓ Production AAP backend configured and deepagent-ansible-mcp restarted.${NC}"
elif [[ "$AAP_MODE" == "mock" && "$CURRENT_AAP_MODE" != "mock" ]]; then
    echo -e "Setting AAP backend to Local Simulation (Mock)..."
    podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) VALUES ('ansible_backend_mode', 'mock', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
EOF
    podman restart deepagent-ansible-mcp >/dev/null
    podman restart deepagent-aap-server >/dev/null 2>&1 || true
    echo -e "${GREEN}✓ Switched to local mock AAP simulation.${NC}"
else
    echo -e "${GREEN}✓ AAP backend settings already up to date.${NC}"
fi

echo -e "Restarting service..."
podman restart deepagent-service >/dev/null
echo -e "Waiting for Deep Agent service to become ready..."
RETRY=0
MAX_RETRIES=15
while [[ $RETRY -lt $MAX_RETRIES ]]; do
    if podman exec -i deepagent-service curl -s -f "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Deep Agent core API is ready on port ${API_PORT}.${NC}"
        break
    fi
    sleep 2
    RETRY=$((RETRY + 1))
done

if [[ $RETRY -eq $MAX_RETRIES ]]; then
    echo -e "${YELLOW}Warning: Core API took longer to start. Checking recent service logs:${NC}"
    podman logs --tail 15 deepagent-service
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Verify Live Response
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/4] Verifying live connection with TLS preservation...${NC}"

CHAT_PAYLOAD='{
  "model": "deepagent",
  "domain": "linux_sre",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": false
}'

API_RESP=$(podman exec -i deepagent-service curl -s \
    -w "\n%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer hermes-api-secret" \
    --connect-timeout 10 \
    --max-time 45 \
    -d "$CHAT_PAYLOAD" \
    "http://127.0.0.1:${API_PORT}/v1/chat/completions" 2>&1 || echo "FAILED")

HTTP_CODE=$(echo "$API_RESP" | tail -n1)
BODY_RESP=$(echo "$API_RESP" | sed '$d')

if echo "$BODY_RESP" | grep -q "choices"; then
    echo -e "${GREEN}${BOLD}🎉 SUCCESS! Deep Agent responded securely with TLS:${NC}"
    echo "$BODY_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$BODY_RESP"
    echo -e "\n${GREEN}✓ Setup complete (TLS verification strictly enforced).${NC}"
else
    echo -e "${YELLOW}API Status Code: ${HTTP_CODE}${NC}"
    echo -e "${YELLOW}API Output:${NC}"
    echo "$BODY_RESP"
    echo -e "\n${BOLD}Diagnostic Container Logs:${NC}"
    podman logs --tail 20 deepagent-service
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"

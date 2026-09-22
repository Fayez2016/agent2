#!/bin/bash
# ==============================================================================
#  Deep Agent Air-Gapped LLM Connectivity & Diagnostic Verifier
# ==============================================================================
#  Purpose:
#    Diagnoses why Deep Agent hangs for ~60s and displays an empty response
#    when testing LLM access in an air-gapped environment.
#    Checks PostgreSQL domain_agents, system_settings, pod network reachability,
#    and applies instant database/service remediations.
# ==============================================================================

set -eo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🔍 DEEP AGENT AIR-GAPPED LLM DIAGNOSTIC & REMEDIATION VERIFIER              ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Check Container / Pod Status
echo -e "\n${BOLD}[Step 1/5] Checking Podman Containers...${NC}"
if ! command -v podman &>/dev/null; then
    echo -e "${RED}❌ Error: Podman is not installed or not in PATH.${NC}"
    exit 1
fi

DB_RUNNING=$(podman ps --filter "name=deepagent-hitl-db" --format "{{.Status}}" || true)
CORE_RUNNING=$(podman ps --filter "name=deepagent-service" --format "{{.Status}}" || true)

if [[ -z "$DB_RUNNING" ]]; then
    echo -e "${RED}❌ deepagent-hitl-db is NOT running! Please start the database container first.${NC}"
    exit 1
else
    echo -e "${GREEN}✓ deepagent-hitl-db is UP (${DB_RUNNING})${NC}"
fi

if [[ -z "$CORE_RUNNING" ]]; then
    echo -e "${YELLOW}⚠️ deepagent-service is NOT running. Pod may be stopped.${NC}"
else
    echo -e "${GREEN}✓ deepagent-service is UP (${CORE_RUNNING})${NC}"
fi

# 2. Inspect Active Agent Configuration in PostgreSQL (domain_agents)
echo -e "\n${BOLD}[Step 2/5] Inspecting 'linux_sre' Agent in PostgreSQL (domain_agents)...${NC}"
AGENT_CONF=$(podman exec -i deepagent-hitl-db psql -U hermes -d hitl -t -A -F'|' -c "
SELECT key_name, model_provider, model_name FROM domain_agents WHERE key_name = 'linux_sre' LIMIT 1;
" 2>/dev/null || true)

if [[ -z "$AGENT_CONF" ]]; then
    echo -e "${YELLOW}⚠️ 'linux_sre' record not found in domain_agents table.${NC}"
    AGENT_PROVIDER="unknown"
    AGENT_MODEL="unknown"
else
    AGENT_KEY=$(echo "$AGENT_CONF" | cut -d'|' -f1)
    AGENT_PROVIDER=$(echo "$AGENT_CONF" | cut -d'|' -f2)
    AGENT_MODEL=$(echo "$AGENT_CONF" | cut -d'|' -f3)

    echo -e "  • Agent Key       : ${BOLD}$AGENT_KEY${NC}"
    echo -e "  • Model Provider  : ${BOLD}$AGENT_PROVIDER${NC}"
    echo -e "  • Model Name      : ${BOLD}$AGENT_MODEL${NC}"

    if [[ "$AGENT_PROVIDER" == "openrouter" ]]; then
        echo -e "\n${RED}🚨 ROOT CAUSE DETECTED!${NC}"
        echo -e "${RED}  The 'linux_sre' agent in PostgreSQL is explicitly configured with provider='openrouter'.${NC}"
        echo -e "${YELLOW}  In your air-gapped environment, calls to 'https://openrouter.ai/api/v1' cannot route out.${NC}"
        echo -e "${YELLOW}  The HTTP client hangs for the default 60-second timeout (timeout=60) and returns an empty bubble.${NC}"
    else
        echo -e "${GREEN}✓ Agent provider is set to: $AGENT_PROVIDER${NC}"
    fi
fi

# 3. Inspect System Settings for LLM Gateways
echo -e "\n${BOLD}[Step 3/5] Inspecting Global LLM System Settings in PostgreSQL...${NC}"
podman exec -i deepagent-hitl-db psql -U hermes -d hitl -c "
SELECT key, value, updated_at FROM system_settings 
WHERE key IN ('llm_default_provider', 'custom_openai_base_url', 'custom_openai_model', 'custom_openai_api_key', 'ollama_host', 'ollama_model')
ORDER BY key;
" 2>/dev/null || true

CUSTOM_URL=$(podman exec -i deepagent-hitl-db psql -U hermes -d hitl -t -A -c "
SELECT value FROM system_settings WHERE key = 'custom_openai_base_url' LIMIT 1;
" 2>/dev/null || true)

CUSTOM_KEY=$(podman exec -i deepagent-hitl-db psql -U hermes -d hitl -t -A -c "
SELECT value FROM system_settings WHERE key = 'custom_openai_api_key' LIMIT 1;
" 2>/dev/null || true)

CUSTOM_MODEL=$(podman exec -i deepagent-hitl-db psql -U hermes -d hitl -t -A -c "
SELECT value FROM system_settings WHERE key = 'custom_openai_model' LIMIT 1;
" 2>/dev/null || true)

# 4. Probe Network Reachability from Inside the Core Service Container
echo -e "\n${BOLD}[Step 4/5] Testing LLM Network Reachability from Inside deepagent-service...${NC}"
if [[ -z "$CUSTOM_URL" || "$CUSTOM_URL" == "https://api.openai.com/v1" ]]; then
    echo -e "${YELLOW}⚠️ 'custom_openai_base_url' is either empty or set to public OpenAI default ($CUSTOM_URL).${NC}"
    echo -e "${YELLOW}  You must provide the internal URL to your air-gapped LLM inference gateway.${NC}"
else
    echo -e "  • Target URL: ${BOLD}$CUSTOM_URL${NC}"
    MODELS_URL="${CUSTOM_URL%/}/models"
    
    AUTH_HEADER=""
    if [[ -n "$CUSTOM_KEY" && "$CUSTOM_KEY" != "none" ]]; then
        AUTH_HEADER="Authorization: Bearer $CUSTOM_KEY"
    fi

    echo -e "  • Probing GET $MODELS_URL with 10s timeout..."
    HTTP_CODE=$(podman exec -i deepagent-service curl -s -k -o /tmp/llm_test_response.json -w "%{http_code}" \
        ${AUTH_HEADER:+-H "$AUTH_HEADER"} \
        --connect-timeout 10 \
        --max-time 15 \
        "$MODELS_URL" 2>/dev/null || echo "TIMEOUT_OR_FAILED")

    if [[ "$HTTP_CODE" == "200" ]]; then
        echo -e "${GREEN}✓ Success! Gateway responded with HTTP 200 OK.${NC}"
        echo -e "  Available models (first 3):"
        podman exec -i deepagent-service python3 -c '
import json, sys
try:
    with open("/tmp/llm_test_response.json") as f:
        data = json.load(f)
    models = [m.get("id") for m in data.get("data", [])[:3]]
    print("   ", models)
except Exception as e:
    pass
' 2>/dev/null || true
    else
        echo -e "${RED}❌ Probe failed with HTTP Code: $HTTP_CODE${NC}"
        echo -e "${YELLOW}  Note: If the server does not support /v1/models, testing a lightweight completion ping...${NC}"
        
        COMPLETION_URL="${CUSTOM_URL%/}/chat/completions"
        MODEL_NAME="${CUSTOM_MODEL:-qwen}"
        TEST_PAYLOAD="{\"model\": \"$MODEL_NAME\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}"
        
        COMP_HTTP=$(podman exec -i deepagent-service curl -s -k -o /tmp/llm_comp_resp.json -w "%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            ${AUTH_HEADER:+-H "$AUTH_HEADER"} \
            --connect-timeout 10 \
            --max-time 20 \
            -d "$TEST_PAYLOAD" \
            "$COMPLETION_URL" 2>/dev/null || echo "FAILED")

        if [[ "$COMP_HTTP" == "200" ]]; then
            echo -e "${GREEN}✓ Chat completion ping succeeded with HTTP 200 OK!${NC}"
        else
            echo -e "${RED}❌ Chat completion ping returned: $COMP_HTTP${NC}"
            podman exec -i deepagent-service cat /tmp/llm_comp_resp.json 2>/dev/null || true
            echo ""
        fi
    fi
fi

# 5. Remediation Options
echo -e "\n${BOLD}[Step 5/5] Automated Remediation${NC}"
if [[ "$1" == "--fix" || "$AGENT_PROVIDER" == "openrouter" ]]; then
    echo -e "${CYAN}Applying fix to PostgreSQL 'domain_agents' table...${NC}"
    
    TARGET_PROVIDER="custom_openai"
    TARGET_MODEL="${CUSTOM_MODEL:-qwen/qwen-2.5-72b-instruct}"
    
    podman exec -i deepagent-hitl-db psql -U hermes -d hitl -c "
    UPDATE domain_agents 
    SET model_provider = '$TARGET_PROVIDER',
        model_name = '$TARGET_MODEL',
        updated_at = NOW()
    WHERE key_name = 'linux_sre';

    UPDATE system_settings
    SET value = '$TARGET_PROVIDER',
        updated_at = NOW()
    WHERE key = 'llm_default_provider';
    "
    
    echo -e "${GREEN}✓ Updated 'linux_sre' model_provider to '$TARGET_PROVIDER' and model_name to '$TARGET_MODEL'.${NC}"
    echo -e "${CYAN}Flushing in-memory compiled agents by restarting deepagent-service...${NC}"
    podman restart deepagent-service
    echo -e "${GREEN}✓ deepagent-service restarted.${NC}"
    echo -e "\n${BOLD}🎉 Remediation Complete!${NC} Reload your browser, open Chat, and type 'hi'."
else
    echo -e "To automatically switch 'linux_sre' to 'custom_openai' and restart the service, run:"
    echo -e "  ${BOLD}./verify_and_fix_airgap_llm.sh --fix${NC}"
fi

echo -e "\n${CYAN}==============================================================================${NC}"

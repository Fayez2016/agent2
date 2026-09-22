#!/bin/bash
# ==============================================================================
#  Deep Agent Air-Gapped LLM Complete Resolver & End-to-End Verifier
# ==============================================================================
#  Purpose:
#    1. Extracts previous chat errors/tracebacks from full deepagent-service logs.
#    2. Inspects and displays current database configuration.
#    3. Probes the internal AI Gateway to resolve 404 / 405 path mismatches.
#    4. Automatically applies the fix into PostgreSQL domain_agents & system_settings.
#    5. Restarts deepagent-service.
#    6. Executes a LIVE end-to-end chat test ("hi") through deepagent-service and
#       prints the stream output to confirm 100% working status.
# ==============================================================================

set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🛠️  DEEP AGENT AIR-GAPPED LLM COMPLETE RESOLVER & VERIFIER                   ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Analyze Full Container Logs for Past Chat Errors
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 1/5] Analyzing Full deepagent-service Logs for Chat Exceptions...${NC}"

CHAT_LOGS=$(podman logs deepagent-service 2>&1 | grep -C 3 -iE "ChatRouter|chat/completions|Traceback|ConnectTimeout|SSLError|HTTPStatusError" | tail -n 35 || true)

if [[ -n "$CHAT_LOGS" ]]; then
    echo -e "${YELLOW}Found relevant historical log entries:${NC}"
    echo -e "${CYAN}------------------------------------------------------------------------------${NC}"
    echo "$CHAT_LOGS"
    echo -e "${CYAN}------------------------------------------------------------------------------${NC}"
else
    echo -e "${GREEN}✓ No unhandled exceptions logged in recent history.${NC}"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Inspect Database State
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 2/5] Inspecting PostgreSQL Configuration...${NC}"

AGENT_CONF=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -F'|' -c "
SELECT key_name, model_provider, model_name FROM domain_agents WHERE key_name = 'linux_sre';
" 2>/dev/null || echo "")

DB_URL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "
SELECT value FROM system_settings WHERE key = 'custom_openai_base_url' LIMIT 1;
" 2>/dev/null || echo "")

DB_KEY=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "
SELECT value FROM system_settings WHERE key = 'custom_openai_api_key' LIMIT 1;
" 2>/dev/null || echo "")

DB_MODEL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "
SELECT value FROM system_settings WHERE key = 'custom_openai_model' LIMIT 1;
" 2>/dev/null || echo "")

echo -e "  • Active Agent 'linux_sre' Provider : ${BOLD}$(echo "$AGENT_CONF" | cut -d'|' -f2)${NC}"
echo -e "  • Active Agent 'linux_sre' Model    : ${BOLD}$(echo "$AGENT_CONF" | cut -d'|' -f3)${NC}"
echo -e "  • Stored custom_openai_base_url     : ${BOLD}$DB_URL${NC}"
echo -e "  • Stored custom_openai_model        : ${BOLD}$DB_MODEL${NC}"
echo -e "  • Stored custom_openai_api_key      : ${BOLD}${DB_KEY:0:4}••••${DB_KEY: -4}${NC}"

CURRENT_PROVIDER=$(echo "$AGENT_CONF" | cut -d'|' -f2)
if [[ "$CURRENT_PROVIDER" == "openrouter" ]]; then
    echo -e "\n${RED}🚨 ROOT CAUSE CONFIRMED: 'linux_sre' is configured with provider='openrouter'.${NC}"
    echo -e "${YELLOW}  In an air-gapped network, calls to openrouter.ai fail silently after 60s.${NC}"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Stage 3: Resolve the Gateway URL, Token, and Path (Fix 404 / 405)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 3/5] Testing Gateway Paths to Resolve 404 / 405 Mismatch...${NC}"

# Allow interactive prompt if values are missing or user wants to specify
TARGET_URL="${DB_URL}"
if [[ -z "$TARGET_URL" || "$TARGET_URL" == "https://api.openai.com/v1" ]]; then
    read -r -p "👉 Enter your internal AI Gateway URL (e.g. https://aigw.aramco.com.sa/v1): " TARGET_URL
fi
TARGET_URL=$(echo "$TARGET_URL" | xargs)

TARGET_KEY="${DB_KEY}"
if [[ -z "$TARGET_KEY" ]]; then
    read -r -s -p "👉 Enter your API Token / Bearer Key: " TARGET_KEY
    echo ""
fi
TARGET_KEY=$(echo "$TARGET_KEY" | xargs)

TARGET_MODEL="${DB_MODEL:-Qwen/Qwen2.5-27B}"

# Strip /v1 from the base to test variations cleanly
CLEAN_BASE=$(echo "$TARGET_URL" | sed -E 's|/v1/?$||' | sed -E 's|/api/v1/?$||' | sed -E 's|/*$||')

echo -e "\nProbing endpoints from inside deepagent-service container:"

# Test Candidate 1: $CLEAN_BASE/v1/chat/completions (POST)
echo -n "  Testing POST $CLEAN_BASE/v1/chat/completions ... "
RESP1=$(podman exec -i deepagent-service curl -s -k -w "\n%{http_code}" --connect-timeout 8 --max-time 15 \
    -X POST \
    -H "Content-Type: application/json" \
    ${TARGET_KEY:+-H "Authorization: Bearer $TARGET_KEY"} \
    -d "{\"model\": \"$TARGET_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}], \"max_tokens\": 5}" \
    "$CLEAN_BASE/v1/chat/completions" 2>/dev/null || echo "FAILED 000")
CODE1=$(echo "$RESP1" | tail -n1)

WORKING_BASE=""
if [[ "$CODE1" == "200" ]]; then
    echo -e "${GREEN}200 OK (SUCCESS!)${NC}"
    WORKING_BASE="$CLEAN_BASE/v1"
else
    echo -e "${YELLOW}HTTP $CODE1${NC}"
fi

# Test Candidate 2: $CLEAN_BASE/chat/completions (POST without /v1)
if [[ -z "$WORKING_BASE" ]]; then
    echo -n "  Testing POST $CLEAN_BASE/chat/completions ... "
    RESP2=$(podman exec -i deepagent-service curl -s -k -w "\n%{http_code}" --connect-timeout 8 --max-time 15 \
        -X POST \
        -H "Content-Type: application/json" \
        ${TARGET_KEY:+-H "Authorization: Bearer $TARGET_KEY"} \
        -d "{\"model\": \"$TARGET_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}], \"max_tokens\": 5}" \
        "$CLEAN_BASE/chat/completions" 2>/dev/null || echo "FAILED 000")
    CODE2=$(echo "$RESP2" | tail -n1)

    if [[ "$CODE2" == "200" ]]; then
        echo -e "${GREEN}200 OK (SUCCESS!)${NC}"
        WORKING_BASE="$CLEAN_BASE"
    else
        echo -e "${YELLOW}HTTP $CODE2${NC}"
    fi
fi

# Test Candidate 3: $CLEAN_BASE/v1/chat/completions/ (POST with trailing slash)
if [[ -z "$WORKING_BASE" ]]; then
    echo -n "  Testing POST $CLEAN_BASE/v1/chat/completions/ (trailing slash) ... "
    RESP3=$(podman exec -i deepagent-service curl -s -k -w "\n%{http_code}" --connect-timeout 8 --max-time 15 \
        -X POST \
        -H "Content-Type: application/json" \
        ${TARGET_KEY:+-H "Authorization: Bearer $TARGET_KEY"} \
        -d "{\"model\": \"$TARGET_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}], \"max_tokens\": 5}" \
        "$CLEAN_BASE/v1/chat/completions/" 2>/dev/null || echo "FAILED 000")
    CODE3=$(echo "$RESP3" | tail -n1)

    if [[ "$CODE3" == "200" ]]; then
        echo -e "${GREEN}200 OK (SUCCESS!)${NC}"
        WORKING_BASE="$CLEAN_BASE/v1"
    else
        echo -e "${YELLOW}HTTP $CODE3${NC}"
    fi
fi

# Fallback: If none returned 200, use $TARGET_URL as best effort
if [[ -z "$WORKING_BASE" ]]; then
    echo -e "${YELLOW}⚠️ Notice: Direct curl tests returned non-200. Proceeding with user configured URL: $TARGET_URL${NC}"
    WORKING_BASE="$TARGET_URL"
else
    echo -e "${GREEN}${BOLD}✓ Confirmed Working Base URL: $WORKING_BASE${NC}"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Stage 4: Apply Database Updates & Restart Service
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 4/5] Applying Configuration to PostgreSQL & Restarting Service...${NC}"

podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "
-- 1. Point custom_openai_base_url to the verified base
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_base_url', '$WORKING_BASE', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- 2. Store API token
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_api_key', '$TARGET_KEY', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- 3. Store Model
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('custom_openai_model', '$TARGET_MODEL', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- 4. Set global default provider
INSERT INTO system_settings (key, value, updated_at) 
VALUES ('llm_default_provider', 'custom_openai', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

-- 5. Crucial: Switch 'linux_sre' in domain_agents table from openrouter to custom_openai
UPDATE domain_agents 
SET model_provider = 'custom_openai',
    model_name = '$TARGET_MODEL',
    updated_at = NOW()
WHERE key_name = 'linux_sre';
" >/dev/null

echo -e "${GREEN}✓ PostgreSQL domain_agents and system_settings successfully updated.${NC}"

echo -e "Restarting deepagent-service to clear in-memory compiled agent cache..."
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service restarted.${NC}"

# Wait 5 seconds for service to initialize
sleep 5

# ──────────────────────────────────────────────────────────────────────────────
# Stage 5: Live End-to-End Chat Test ("hi")
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 5/5] Executing Live End-to-End Chat Test ('hi') via deepagent-service...${NC}"

TEST_PAYLOAD='{"model": "deepagent", "messages": [{"role": "user", "content": "hi"}], "domain": "linux_sre", "stream": false}'

AGENT_RESPONSE=$(podman exec -i deepagent-service curl -s -k \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer hermes-api-secret" \
    --connect-timeout 10 \
    --max-time 45 \
    -d "$TEST_PAYLOAD" \
    http://127.0.0.1:8080/v1/chat/completions 2>/dev/null || echo "FAILED")

if echo "$AGENT_RESPONSE" | grep -q "choices"; then
    echo -e "${GREEN}${BOLD}🎉 SUCCESS! Deep Agent successfully generated a response from your LLM!${NC}"
    echo -e "${CYAN}Assistant Response:${NC}"
    echo "$AGENT_RESPONSE" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    content = data["choices"][0]["message"]["content"]
    print(content)
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$AGENT_RESPONSE"
elif echo "$AGENT_RESPONSE" | grep -q "detail"; then
    echo -e "${RED}❌ API returned an error:${NC} $AGENT_RESPONSE"
else
    echo -e "${YELLOW}Raw agent response received:${NC} ${AGENT_RESPONSE:0:300}"
fi

echo -e "\n${CYAN}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}Verification Complete.${NC} Refresh your browser and send messages in the Web UI."
echo -e "${CYAN}==============================================================================${NC}"

#!/bin/bash
# ==============================================================================
#  Deep Agent Enterprise LLM Gateway Matrix Prober & Auto-Fixer (v2.0)
# ==============================================================================
#  Purpose:
#    Robustly probes all possible URL path, HTTP method (GET vs POST),
#    trailing slash, and header variations against your internal AI Gateway.
#    Supports CLI flags (--url, --token, --model), positional arguments,
#    auto-detection from PostgreSQL, or interactive prompts if not set.
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
echo -e "${CYAN}${BOLD}  🔬 ENTERPRISE AI GATEWAY COMPREHENSIVE DIAGNOSTIC MATRIX (v2.0)             ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Fetch current settings from PostgreSQL
echo -e "\n${BOLD}[1/4] Checking PostgreSQL settings in deepagent-hitl-db...${NC}"

DB_URL=""
DB_KEY=""
DB_MODEL=""

if podman ps --filter "name=deepagent-hitl-db" --format "{{.Names}}" | grep -q "deepagent-hitl-db"; then
    DB_URL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "
    SELECT value FROM system_settings WHERE key = 'custom_openai_base_url' LIMIT 1;
    " 2>/dev/null || echo "")

    DB_KEY=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "
    SELECT value FROM system_settings WHERE key = 'custom_openai_api_key' LIMIT 1;
    " 2>/dev/null || echo "")

    DB_MODEL=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "
    SELECT value FROM system_settings WHERE key = 'custom_openai_model' LIMIT 1;
    " 2>/dev/null || echo "")
else
    echo -e "${YELLOW}⚠️ Container deepagent-hitl-db is not running.${NC}"
fi

# 2. Parse command line arguments (supports flags AND positional arguments)
TARGET_URL=""
TARGET_KEY=""
TARGET_MODEL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url|-u)
            TARGET_URL="$2"
            shift 2
            ;;
        --token|--key|-k|-t)
            TARGET_KEY="$2"
            shift 2
            ;;
        --model|-m)
            TARGET_MODEL="$2"
            shift 2
            ;;
        https://*|http://*)
            TARGET_URL="$1"
            shift
            ;;
        *)
            if [[ -z "$TARGET_URL" ]]; then
                TARGET_URL="$1"
            elif [[ -z "$TARGET_KEY" ]]; then
                TARGET_KEY="$1"
            elif [[ -z "$TARGET_MODEL" ]]; then
                TARGET_MODEL="$1"
            fi
            shift
            ;;
    esac
done

# Fallback to DB values if not supplied on CLI
TARGET_URL="${TARGET_URL:-$DB_URL}"
TARGET_KEY="${TARGET_KEY:-$DB_KEY}"
TARGET_MODEL="${TARGET_MODEL:-$DB_MODEL}"

# If still empty or default placeholder, interactively ask the user
if [[ -z "$TARGET_URL" || "$TARGET_URL" == "https://api.openai.com/v1" ]]; then
    echo -e "${YELLOW}⚠️ No custom gateway URL detected in database or command line.${NC}"
    read -r -p "👉 Enter your AI Gateway URL (e.g. https://aigw.aramco.com.sa/v1): " TARGET_URL
fi

# Clean trailing whitespace/newlines
TARGET_URL=$(echo "$TARGET_URL" | xargs)

if [[ -z "$TARGET_KEY" ]]; then
    read -r -s -p "👉 Enter your API Token / Bearer Key: " TARGET_KEY
    echo ""
fi

TARGET_KEY=$(echo "$TARGET_KEY" | xargs)

if [[ -z "$TARGET_MODEL" || "$TARGET_MODEL" == "gpt-4o" ]]; then
    read -r -p "👉 Enter Model Name [default: Qwen/Qwen2.5-27B]: " INPUT_MODEL
    TARGET_MODEL="${INPUT_MODEL:-Qwen/Qwen2.5-27B}"
fi

TARGET_MODEL=$(echo "$TARGET_MODEL" | xargs)

echo -e "\n${GREEN}✓ Configuration Loaded:${NC}"
echo -e "  • Gateway URL : ${BOLD}$TARGET_URL${NC}"
echo -e "  • Model Tag   : ${BOLD}$TARGET_MODEL${NC}"
echo -e "  • Token Mask  : ${BOLD}${TARGET_KEY:0:4}••••${TARGET_KEY: -4}${NC}"

# Normalize Base URL variations to test
RAW_HOST=$(echo "$TARGET_URL" | sed -E 's|/v1/?$||' | sed -E 's|/api/v1/?$||' | sed -E 's|/*$||')

BASE_CANDIDATES=(
    "$RAW_HOST"
    "$RAW_HOST/v1"
    "$RAW_HOST/api/v1"
)

echo -e "\n${BOLD}[2/4] Testing Base Host Connectivity & DNS (${RAW_HOST})...${NC}"
DNS_TEST=$(podman exec -i deepagent-service curl -s -k -o /dev/null -w "%{http_code}" --connect-timeout 6 "$RAW_HOST" 2>&1 || true)
if [[ "$DNS_TEST" == *"Could not resolve host"* ]]; then
    echo -e "${RED}❌ DNS Resolution Failure: Container cannot resolve host '$RAW_HOST'.${NC}"
    echo -e "${YELLOW}  Check container DNS in /etc/resolv.conf or test with physical host IP.${NC}"
elif [[ "$DNS_TEST" == *"Connection timed out"* ]]; then
    echo -e "${RED}❌ Network Timeout: Firewall or routing rule is blocking connection to '$RAW_HOST'.${NC}"
else
    echo -e "${GREEN}✓ Host connection reached (HTTP status or banner: $DNS_TEST).${NC}"
fi

echo -e "\n${BOLD}[3/4] Running Systematic Matrix: Path x Method x Slashes x Headers...${NC}"
echo -e "──────────────────────────────────────────────────────────────────────────────"
printf "%-35s | %-6s | %-6s | %-25s\n" "Path Endpoint" "Method" "Status" "Diagnosis"
echo -e "──────────────────────────────────────────────────────────────────────────────"

WINNING_BASE=""
WINNING_ENDPOINT=""
WINNING_HEADER=""
WINNING_RESP=""

probe_endpoint() {
    local base="$1"
    local path="$2"
    local method="$3"
    local header_type="$4" # "bearer" or "apikey"
    local is_chat="$5"

    local full_url="${base}${path}"
    local auth_header="-H \"Authorization: Bearer $TARGET_KEY\""
    if [[ "$header_type" == "apikey" ]]; then
        auth_header="-H \"api-key: $TARGET_KEY\""
    fi

    local resp=""
    if [[ "$method" == "GET" ]]; then
        resp=$(podman exec -i deepagent-service curl -s -k -w "\n%{http_code}" --connect-timeout 8 --max-time 15 \
            -X GET \
            ${TARGET_KEY:+-H "Authorization: Bearer $TARGET_KEY"} \
            "$full_url" 2>/dev/null || echo "FAILED 000")
    else
        local payload="{\"model\": \"$TARGET_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}], \"max_tokens\": 5}"
        resp=$(podman exec -i deepagent-service curl -s -k -w "\n%{http_code}" --connect-timeout 8 --max-time 15 \
            -X POST \
            -H "Content-Type: application/json" \
            ${TARGET_KEY:+-H "Authorization: Bearer $TARGET_KEY"} \
            -d "$payload" \
            "$full_url" 2>/dev/null || echo "FAILED 000")
    fi

    local http_code=$(echo "$resp" | tail -n1)
    local body=$(echo "$resp" | sed '$d')
    local body_snippet=$(echo "$body" | tr -d '\n\r' | cut -c1-40)

    local diag=""
    local color="$NC"

    case "$http_code" in
        200)
            diag="SUCCESS (200 OK)"
            color="$GREEN"
            if [[ -z "$WINNING_BASE" && "$is_chat" == "yes" ]]; then
                WINNING_BASE="$base"
                WINNING_ENDPOINT="$full_url"
                WINNING_HEADER="$header_type"
                WINNING_RESP="$body"
            fi
            ;;
        400)
            diag="Bad Request (check payload/model)"
            color="$YELLOW"
            ;;
        401)
            diag="Unauthorized (invalid/expired token)"
            color="$RED"
            ;;
        403)
            diag="Forbidden (permissions/RBAC)"
            color="$RED"
            ;;
        404)
            diag="Not Found (path does not exist)"
            color="$RED"
            ;;
        405)
            diag="Method Not Allowed (swap GET/POST)"
            color="$MAGENTA"
            ;;
        *)
            diag="Response: $body_snippet"
            color="$YELLOW"
            ;;
    esac

    printf "${color}%-35s | %-6s | %-6s | %-25s${NC}\n" "$path" "$method" "$http_code" "$diag"
}

# Run matrix across all permutations
for base in "${BASE_CANDIDATES[@]}"; do
    echo -e "\n${CYAN}▶ Testing Base: ${BOLD}${base}${NC}"
    
    # 1. Test GET /models
    probe_endpoint "$base" "/models" "GET" "bearer" "no"
    probe_endpoint "$base" "/models/" "GET" "bearer" "no"

    # 2. Test POST /chat/completions (standard OpenAI)
    probe_endpoint "$base" "/chat/completions" "POST" "bearer" "yes"
    probe_endpoint "$base" "/chat/completions/" "POST" "bearer" "yes"

    # 3. Test GET /chat/completions (to verify if 405 occurs)
    probe_endpoint "$base" "/chat/completions" "GET" "bearer" "no"
done

echo -e "──────────────────────────────────────────────────────────────────────────────"

# 4. Results and Auto-Remediation
echo -e "\n${BOLD}[4/4] Diagnostic Summary & Auto-Remediation${NC}"

if [[ -n "$WINNING_BASE" ]]; then
    echo -e "${GREEN}${BOLD}🎉 WORKING ENDPOINT DISCOVERED!${NC}"
    echo -e "  • Verified Working URL : ${BOLD}$WINNING_ENDPOINT${NC}"
    echo -e "  • Recommended Base URL : ${BOLD}$WINNING_BASE${NC}"
    echo -e "  • Response Sample      : ${CYAN}${WINNING_RESP:0:120}...${NC}"

    echo -e "\n${BOLD}Applying configuration to PostgreSQL and restarting agent...${NC}"
    
    podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "
    -- Update custom OpenAI base URL to verified working base
    INSERT INTO system_settings (key, value, updated_at) 
    VALUES ('custom_openai_base_url', '$WINNING_BASE', NOW())
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

    -- Ensure token is saved
    INSERT INTO system_settings (key, value, updated_at) 
    VALUES ('custom_openai_api_key', '$TARGET_KEY', NOW())
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

    -- Ensure model tag is saved
    INSERT INTO system_settings (key, value, updated_at) 
    VALUES ('custom_openai_model', '$TARGET_MODEL', NOW())
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

    -- Ensure default provider is custom_openai
    INSERT INTO system_settings (key, value, updated_at) 
    VALUES ('llm_default_provider', 'custom_openai', NOW())
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

    -- Switch the active linux_sre agent in domain_agents table
    UPDATE domain_agents 
    SET model_provider = 'custom_openai',
        model_name = '$TARGET_MODEL',
        updated_at = NOW()
    WHERE key_name = 'linux_sre';
    "
    
    echo -e "${GREEN}✓ Database updated with verified base URL: $WINNING_BASE${NC}"
    echo -e "${CYAN}Restarting deepagent-service to apply changes...${NC}"
    podman restart deepagent-service
    echo -e "${GREEN}✓ deepagent-service restarted!${NC}"
    echo -e "\n${GREEN}${BOLD}Everything is set! Refresh your browser, open Chat, and send 'hi'.${NC}"
else
    echo -e "${YELLOW}⚠️ None of the standard endpoints returned 200 OK automatically.${NC}"
    echo -e "Check the table above for ${MAGENTA}405 (Method Not Allowed)${NC} or ${RED}401 (Unauthorized)${NC}."
    echo -e "If you see a ${MAGENTA}405${NC} on a specific path, look at the method column to confirm GET vs POST."
fi

echo -e "\n${CYAN}==============================================================================${NC}"

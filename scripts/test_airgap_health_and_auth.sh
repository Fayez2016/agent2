#!/bin/bash
# ==============================================================================
# Script: test_airgap_health_and_auth.sh
# Purpose: Pinpoint exact failure point for WebUI / Login / API communication.
# ==============================================================================

set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}       DeepAgent Detailed API & Auth Diagnostic     ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Test 1: Port 8642 Direct Login
echo -e "\n${YELLOW}>>> [1/4] Testing Direct Backend Login (Port 8642)...${NC}"
resp_direct=$(podman exec -i deepagent-service curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST http://127.0.0.1:8642/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' 2>&1)
status_direct=$(echo "$resp_direct" | grep "HTTP_STATUS:" | cut -d':' -f2)
body_direct=$(echo "$resp_direct" | grep -v "HTTP_STATUS:")

if [ "$status_direct" == "200" ]; then
    echo -e "${GREEN}[OK] Direct Backend (8642) Login: HTTP 200 OK${NC}"
else
    echo -e "${RED}[FAIL] Direct Backend (8642) Login: HTTP $status_direct${NC}"
    echo "Body: $body_direct"
fi

# Test 2: Nginx Proxy to Backend (8443)
echo -e "\n${YELLOW}>>> [2/4] Testing HTTPS Reverse Proxy Login (Port 8443)...${NC}"
resp_proxy=$(curl -k -s -w "\nHTTP_STATUS:%{http_code}" -X POST https://127.0.0.1:8443/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' 2>&1)
status_proxy=$(echo "$resp_proxy" | grep "HTTP_STATUS:" | cut -d':' -f2)
body_proxy=$(echo "$resp_proxy" | grep -v "HTTP_STATUS:")

if [ "$status_proxy" == "200" ]; then
    echo -e "${GREEN}[OK] HTTPS Proxy (8443) Login: HTTP 200 OK${NC}"
else
    echo -e "${RED}[FAIL] HTTPS Proxy (8443) Login: HTTP $status_proxy${NC}"
    echo "Body: $body_proxy"
    if [[ "$body_proxy" =~ "<html" ]]; then
        echo -e "${RED}--> CRITICAL: Proxy returned HTML instead of JSON! This causes 'Unexpected token < ...' in browser!${NC}"
    fi
fi

# Test 3: Chat Completions API
echo -e "\n${YELLOW}>>> [3/4] Testing Chat Completions Endpoint (/v1/chat/completions)...${NC}"
chat_resp=$(curl -k -s -w "\nHTTP_STATUS:%{http_code}" -X POST https://127.0.0.1:8443/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{"domain":"linux_sre","messages":[{"role":"user","content":"ping"}]}' 2>&1)
chat_status=$(echo "$chat_resp" | grep "HTTP_STATUS:" | cut -d':' -f2)
chat_body=$(echo "$chat_resp" | grep -v "HTTP_STATUS:")

if [ "$chat_status" == "200" ]; then
    echo -e "${GREEN}[OK] Chat API: HTTP 200 OK${NC}"
else
    echo -e "${RED}[FAIL] Chat API: HTTP $chat_status${NC}"
    echo "Body: $chat_body"
fi

# Test 4: Container Log Inspection
echo -e "\n${YELLOW}>>> [4/4] Last 20 lines of deepagent-service logs:${NC}"
podman logs --tail 20 deepagent-service

echo -e "\n${BLUE}====================================================${NC}"

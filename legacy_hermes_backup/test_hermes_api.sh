#!/usr/bin/env bash

# Test Script for Hermes REST API and Ansible MCP Tools

API_URL="http://localhost:8642/v1/chat/completions"
API_KEY="hermes-api-secret"

PROMPT="${1:-Execute tool ansible_get_server_info for hostlist test1}"

echo "=========================================================================="
echo " Sending Request to Hermes Agent REST API"
echo " Prompt: ${PROMPT}"
echo "=========================================================================="

curl -s -X POST "${API_URL}" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hermes-agent",
    "messages": [
      {
        "role": "user",
        "content": "'"${PROMPT}"'"
      }
    ]
  }' | python3 -m json.tool

echo ""
echo "Done."

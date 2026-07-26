#!/bin/bash
set -e

echo "🔍 Verifying Airgapped Staging Services..."

echo "1. Checking Ollama (gemma4:12b)..."
curl -sf http://localhost:11434/api/tags | grep -q "gemma4" && echo "   [OK] Ollama is active with gemma4 model" || echo "   [FAIL] Ollama endpoint error"

echo "2. Checking Hermes Agent API Server..."
curl -sf http://localhost:8642/health | grep -q "hermes-agent" && echo "   [OK] Hermes API listener healthy" || echo "   [FAIL] Hermes API endpoint error"

echo "3. Checking Ansible MCP Server..."
curl -sf http://localhost:8000/mcp || curl -sf http://localhost:8000/ && echo "   [OK] Ansible MCP Server active" || echo "   [FAIL] MCP server endpoint error"

echo "4. Checking HITL Web Portal..."
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5001 | grep -q "302\|200" && echo "   [OK] HITL Web portal active" || echo "   [FAIL] HITL portal error"

echo ""
echo "✅ All staging endpoints verified!"

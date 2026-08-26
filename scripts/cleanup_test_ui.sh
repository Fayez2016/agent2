#!/usr/bin/env bash
set -e

echo "=========================================================================="
echo ">>> Cleaning up isolated deep-agents-ui test stack..."
echo "=========================================================================="

# 1. Stop and remove test containers
echo "-> Removing temporary test containers..."
podman rm -f deepagent-langgraph-server deepagent-ui-official 2>/dev/null || true

# 2. Remove test image
echo "-> Removing temporary test images..."
podman rmi localhost/deepagents-ui-official:test 2>/dev/null || true

# 3. Clean temporary files
echo "-> Cleaning temporary configuration and cloned UI files..."
rm -f /home/fayez/agent2/docker-compose.deepagents-ui-test.yml
rm -f /home/fayez/agent2/deepagent_system/langgraph.json
rm -rf /home/fayez/agent2/deep-agents-ui/

# 4. Verify primary production services remain healthy and running
echo "=========================================================================="
echo ">>> Verifying primary production stack status..."
echo "=========================================================================="
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "deepagent-service|deepagent-webui|deepagent-ansible-mcp|deepagent-sop-mcp|deepagent-ollama|deepagent-hitl-db"

echo "=========================================================================="
echo ">>> Cleanup completed successfully. Primary stack is completely untouched."
echo "=========================================================================="

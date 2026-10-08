#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo " 🚀 Applying Phase 2: Native MCP FastMCP Tools & Timeout Update"
echo "=================================================================="

# 1. Update deepagent_system/ansible_mcp_server.py in deepagent-ansible-mcp container
echo ">>> [1/3] Copying updated ansible_mcp_server.py into container..."
podman cp deepagent_system/ansible_mcp_server.py deepagent-ansible-mcp:/app/ansible_mcp_server.py
podman restart deepagent-ansible-mcp

# 2. Update deepagent_system/app/agent_engine.py in deepagent-service container
echo ">>> [2/3] Copying updated agent_engine.py into deepagent-service..."
podman cp deepagent_system/app/agent_engine.py deepagent-service:/app/app/agent_engine.py
podman restart deepagent-service

# 3. Update mock_aap.py in deepagent-aap-server container
echo ">>> [3/3] Copying updated mock_aap.py into deepagent-aap-server..."
podman cp deepagent_system/mock_aap.py deepagent-aap-server:/app/mock_aap.py
podman restart deepagent-aap-server

sleep 4
echo "✓ All target containers updated and restarted."

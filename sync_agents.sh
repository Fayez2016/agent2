#!/usr/bin/env bash
# ==============================================================================
# 🔄 Deep Agent: Declarative YAML -> Database Sync Script
# ==============================================================================
# Usage:
#   ./sync_agents.sh [path/to/agents_fleet.yaml]
#
# What it does:
#   1. Locates config/agents_fleet.yaml.
#   2. Runs scripts/sync_agents.py inside deepagent-service (no host deps).
#   3. Syncs PostgreSQL (domain_agents, domain_subagents, domain_skills).
#   4. Restarts deepagent-service so in-memory agent recompiles immediately.
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${1:-${SCRIPT_DIR}/config/agents_fleet.yaml}"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 🔄 DEEP AGENT: DECLARATIVE YAML CONFIGURATION SYNC                          ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Error: Configuration file not found at: ${CONFIG_FILE}${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Reading configuration: ${BOLD}${CONFIG_FILE}${NC}"

# Copy the yaml config and sync script into deepagent-service container
podman cp "${CONFIG_FILE}" deepagent-service:/app/config_to_sync.yaml
podman cp "${SCRIPT_DIR}/scripts/sync_agents.py" deepagent-service:/app/sync_agents.py

# Execute the sync inside the container
podman exec -i deepagent-service python3 /app/sync_agents.py /app/config_to_sync.yaml

# Restart deepagent-service to reload in-memory LangGraph agent
echo -e "\n${BOLD}Reloading deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
echo -e "${GREEN}✓ deepagent-service reloaded.${NC}"

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 Synchronization Complete! Database and Studio UI are 100% Up to Date.     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

#!/usr/bin/env bash
# ==============================================================================
# Script: diagnose_long_patch_job.sh
# Purpose: Inspect exactly what the Agent, MCP server, and AAP did during
#          the 30-minute patch job and diagnose why the workflow halted.
# ==============================================================================

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🔍 DEEP AGENT PATCHING WORKFLOW & TIMEOUT DIAGNOSTIC                        ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Check Container Health
echo -e "\n${BOLD}[1/5] Checking container status...${NC}"
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "deepagent|NAMES"

# 2. Check Database HITL / Action Logs for the Patch Job
echo -e "\n${BOLD}[2/5] Inspecting recent job requests and approval status in PostgreSQL...${NC}"
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c \
  "SELECT id, action_name, status, requested_at, resolved_at FROM hitl_requests ORDER BY id DESC LIMIT 5;"

# 3. Check Ansible MCP Logs (Did AAP finish and return to MCP?)
echo -e "\n${BOLD}[3/5] Inspecting Ansible MCP logs around the patch execution...${NC}"
podman logs --tail 40 deepagent-ansible-mcp | grep -E -i "patch|job|resolved|finished|completed|error|exception" || podman logs --tail 25 deepagent-ansible-mcp

# 4. Check DeepAgent Service Logs (Did LLM receive tool output or did it timeout?)
echo -e "\n${BOLD}[4/5] Inspecting Core Service logs (last 50 lines)...${NC}"
podman logs --tail 50 deepagent-service

# 5. Check Active Threads & Messages in Database
echo -e "\n${BOLD}[5/5] Checking latest chat thread history...${NC}"
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c \
  "SELECT id, thread_id, role, LEFT(content, 80) AS preview, created_at FROM thread_messages ORDER BY id DESC LIMIT 6;"

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
